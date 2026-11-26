"""Train the telecom churn model and export a versioned artifact.

Usage (from the repo root):  python model/train.py
"""
import argparse
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SEED = 42
MODEL_VERSION = "1.0.0"

NUMERIC = ["SeniorCitizen", "tenure", "MonthlyCharges", "TotalCharges"]
CATEGORICAL = [
    "gender", "Partner", "Dependents", "PhoneService", "MultipleLines",
    "InternetService", "OnlineSecurity", "OnlineBackup", "DeviceProtection",
    "TechSupport", "StreamingTV", "StreamingMovies", "Contract",
    "PaperlessBilling", "PaymentMethod",
]
FEATURES = NUMERIC + CATEGORICAL


def load(path):
    df = pd.read_csv(path)
    # TotalCharges contains blank strings for tenure=0 customers
    df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce")
    y = (df["Churn"] == "Yes").astype(int)
    return df[FEATURES], y


def build_model():
    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                          ("sc", StandardScaler())]), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])
    clf = LogisticRegression(max_iter=1000, random_state=SEED)
    return Pipeline([("pre", pre), ("clf", clf)])


def evaluate(model, X, y):
    proba = model.predict_proba(X)[:, 1]
    pred = (proba >= 0.5).astype(int)
    return {
        "auc": round(float(roc_auc_score(y, proba)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/telco_churn.csv")
    ap.add_argument("--out-dir", default="model")
    args = ap.parse_args()

    X, y = load(args.data)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=SEED
    )

    # Naive baseline: always predict the majority class
    baseline = DummyClassifier(strategy="prior").fit(X_train, y_train)
    base_metrics = evaluate(baseline, X_test, y_test)

    model = build_model().fit(X_train, y_train)
    metrics = evaluate(model, X_test, y_test)

    # Single-row inference latency on CPU
    row = X_test.iloc[[0]]
    times = []
    for _ in range(200):
        t0 = time.perf_counter()
        model.predict_proba(row)
        times.append((time.perf_counter() - t0) * 1000)
    latency_ms = round(float(np.median(times)), 2)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    artifact = out / f"model-{MODEL_VERSION}.joblib"
    joblib.dump(
        {
            "model_version": MODEL_VERSION,
            "feature_columns": FEATURES,
            "pipeline": model,
            "metrics": metrics,
        },
        artifact,
    )
    size_mb = round(artifact.stat().st_size / 1e6, 3)

    report = {
        "model_version": MODEL_VERSION,
        "seed": SEED,
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "test_churn_rate": round(float(y_test.mean()), 4),
        "baseline_majority_class": base_metrics,
        "logistic_regression": metrics,
        "median_inference_ms": latency_ms,
        "artifact_size_mb": size_mb,
    }
    (out / "metrics.json").write_text(json.dumps(report, indent=2))

    print(json.dumps(report, indent=2))
    print(f"Saved {artifact}")


if __name__ == "__main__":
    main()
