"""Churn prediction API: /health, /version, /predict, /metrics."""
import os
import threading
import time
from contextlib import asynccontextmanager

import joblib
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, Field

API_VERSION = "1.0.0"
MODEL_PATH = os.getenv("MODEL_PATH", "model-1.0.0.joblib")

# Azure Monitor telemetry: only when a connection string is configured
if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor()

state = {"bundle": None, "load_seconds": None}
stats = {"calls": 0, "errors": 0, "total_ms": 0.0}
lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.perf_counter()
    state["bundle"] = joblib.load(MODEL_PATH)
    state["load_seconds"] = round(time.perf_counter() - t0, 3)
    yield


app = FastAPI(title="Churn API", version=API_VERSION, lifespan=lifespan)


class Customer(BaseModel):
    gender: str = Field(min_length=1)
    SeniorCitizen: int = Field(ge=0, le=1)
    Partner: str = Field(min_length=1)
    Dependents: str = Field(min_length=1)
    tenure: int = Field(ge=0, le=100)
    PhoneService: str = Field(min_length=1)
    MultipleLines: str = Field(min_length=1)
    InternetService: str = Field(min_length=1)
    OnlineSecurity: str = Field(min_length=1)
    OnlineBackup: str = Field(min_length=1)
    DeviceProtection: str = Field(min_length=1)
    TechSupport: str = Field(min_length=1)
    StreamingTV: str = Field(min_length=1)
    StreamingMovies: str = Field(min_length=1)
    Contract: str = Field(min_length=1)
    PaperlessBilling: str = Field(min_length=1)
    PaymentMethod: str = Field(min_length=1)
    MonthlyCharges: float = Field(ge=0)
    TotalCharges: float | None = Field(default=None, ge=0)


class Prediction(BaseModel):
    churn: bool
    probability: float
    model_version: str
    duration_ms: float


@app.get("/health")
def health():
    ok = state["bundle"] is not None
    return {"status": "ok" if ok else "loading", "model_load_seconds": state["load_seconds"]}


@app.get("/version")
def version():
    b = state["bundle"]
    return {"api_version": API_VERSION, "model_version": b["model_version"] if b else None}


@app.post("/predict", response_model=Prediction)
def predict(customer: Customer):
    t0 = time.perf_counter()
    try:
        b = state["bundle"]
        row = pd.DataFrame([customer.model_dump()])[b["feature_columns"]]
        proba = float(b["pipeline"].predict_proba(row)[0, 1])
    except Exception:
        with lock:
            stats["errors"] += 1
        raise
    ms = (time.perf_counter() - t0) * 1000
    with lock:
        stats["calls"] += 1
        stats["total_ms"] += ms
    return Prediction(
        churn=proba >= 0.5,
        probability=round(proba, 4),
        model_version=b["model_version"],
        duration_ms=round(ms, 2),
    )


@app.get("/metrics")
def metrics():
    with lock:
        calls = stats["calls"]
        avg = stats["total_ms"] / calls if calls else 0.0
        return {"calls": calls, "errors": stats["errors"], "avg_latency_ms": round(avg, 2)}
