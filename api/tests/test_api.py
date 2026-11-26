import os
from pathlib import Path

# Point the app at the real model before importing it
MODEL = Path(__file__).resolve().parents[2] / "model" / "model-1.0.0.joblib"
os.environ["MODEL_PATH"] = str(MODEL)
os.environ.pop("APPLICATIONINSIGHTS_CONNECTION_STRING", None)

import pytest
from fastapi.testclient import TestClient
from main import app

VALID = {
    "gender": "Female", "SeniorCitizen": 0, "Partner": "Yes", "Dependents": "No",
    "tenure": 1, "PhoneService": "No", "MultipleLines": "No phone service",
    "InternetService": "DSL", "OnlineSecurity": "No", "OnlineBackup": "Yes",
    "DeviceProtection": "No", "TechSupport": "No", "StreamingTV": "No",
    "StreamingMovies": "No", "Contract": "Month-to-month", "PaperlessBilling": "Yes",
    "PaymentMethod": "Electronic check", "MonthlyCharges": 29.85, "TotalCharges": 29.85,
}


@pytest.fixture(scope="module")
def client():
    # The context manager runs the lifespan, which loads the model
    with TestClient(app) as c:
        yield c


def test_predict_success(client):
    r = client.post("/predict", json=VALID)
    assert r.status_code == 200
    body = r.json()
    assert 0.0 <= body["probability"] <= 1.0
    assert isinstance(body["churn"], bool)
    assert body["model_version"] == "1.0.0"


def test_predict_invalid_input_returns_422(client):
    bad = {**VALID, "tenure": -5}
    r = client.post("/predict", json=bad)
    assert r.status_code == 422


def test_predict_missing_body_returns_422(client):
    r = client.post("/predict")
    assert r.status_code == 422


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_version(client):
    r = client.get("/version")
    assert r.status_code == 200
    assert r.json() == {"api_version": "1.0.0", "model_version": "1.0.0"}
