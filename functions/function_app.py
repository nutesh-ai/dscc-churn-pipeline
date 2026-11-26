"""Event-driven pipeline: dispatcher (Event Grid) -> queue -> worker -> API -> Blob + Cosmos."""
import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from functools import cache

import azure.functions as func
import httpx
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from azure.storage.queue import QueueClient, TextBase64EncodePolicy

app = func.FunctionApp()
logger = logging.getLogger(__name__)

REQUIRED_FIELDS = (
    "gender", "SeniorCitizen", "Partner", "Dependents", "tenure", "PhoneService",
    "MultipleLines", "InternetService", "OnlineSecurity", "OnlineBackup",
    "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies", "Contract",
    "PaperlessBilling", "PaymentMethod", "MonthlyCharges",
)
NUMERIC_FIELDS = ("SeniorCitizen", "tenure", "MonthlyCharges")
QUEUE_NAME = "inference-requests"

# One reused HTTP client with explicit timeouts (the API may need a cold start)
http = httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0))


@cache
def credential():
    return DefaultAzureCredential()


@cache
def blob_service():
    conn = os.getenv("STORAGE_CONN")  # local Azurite only
    if conn:
        return BlobServiceClient.from_connection_string(conn)
    account = os.environ["STORAGE_ACCOUNT"]
    return BlobServiceClient(f"https://{account}.blob.core.windows.net", credential=credential())


@cache
def queue_client():
    policy = TextBase64EncodePolicy()  # the Functions queue trigger expects base64
    conn = os.getenv("STORAGE_CONN")
    if conn:
        return QueueClient.from_connection_string(conn, QUEUE_NAME, message_encode_policy=policy)
    account = os.environ["STORAGE_ACCOUNT"]
    return QueueClient(
        f"https://{account}.queue.core.windows.net", QUEUE_NAME,
        credential=credential(), message_encode_policy=policy,
    )


@cache
def cosmos_container():
    endpoint = os.getenv("COSMOS_ENDPOINT")
    if not endpoint:
        return None  # local runs without Cosmos
    client = CosmosClient(endpoint, credential=credential())
    return client.get_database_client("pipeline").get_container_client("inferences")


def validate(payload):
    """Return a rejection reason, or None when the payload is acceptable."""
    if not isinstance(payload, dict):
        return "JSON root must be an object"
    missing = [f for f in REQUIRED_FIELDS if f not in payload]
    if missing:
        return "missing fields: " + ", ".join(missing[:5])
    for f in NUMERIC_FIELDS:
        if isinstance(payload[f], bool) or not isinstance(payload[f], (int, float)):
            return f"field {f} must be a number"
    return None


def reject(name, reason, raw=None):
    rejected = blob_service().get_container_client("rejected")
    if raw is not None:
        rejected.upload_blob(name, raw, overwrite=True, metadata={"reason": reason[:200]})
    else:
        rejected.upload_blob(name + ".reason.txt", reason.encode(), overwrite=True)
    logger.warning("REJECTED %s: %s", name, reason)


@app.function_name("dispatcher")
@app.event_grid_trigger(arg_name="event")
def dispatcher(event: func.EventGridEvent):
    data = event.get_json()
    name = event.subject.split("/blobs/", 1)[1]
    etag = data.get("eTag", "")
    size = int(data.get("contentLength", 0))
    max_bytes = int(os.getenv("MAX_FILE_BYTES", "20000"))

    raw = None
    if size <= max_bytes:
        raw = blob_service().get_blob_client("input", name).download_blob().readall()

    if not name.lower().endswith(".json"):
        return reject(name, "unsupported extension (expected .json)", raw)
    if raw is None:
        return reject(name, f"file too large ({size} bytes, max {max_bytes})")
    try:
        payload = json.loads(raw)
    except ValueError:
        return reject(name, "invalid JSON", raw)
    reason = validate(payload)
    if reason:
        return reject(name, reason, raw)

    message = {
        "blobName": name,
        "etag": etag,
        "size": size,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    queue_client().send_message(json.dumps(message))
    logger.info("QUEUED %s", name)


@app.function_name("worker")
@app.queue_trigger(arg_name="msg", queue_name=QUEUE_NAME, connection="AzureWebJobsStorage")
def worker(msg: func.QueueMessage):
    job = json.loads(msg.get_body().decode())
    name, etag = job["blobName"], job["etag"]
    # Idempotence key: same file + same version always maps to the same id
    item_id = hashlib.sha256(f"{name}|{etag}".encode()).hexdigest()[:32]

    raw = blob_service().get_blob_client("input", name).download_blob().readall()
    started = datetime.now(UTC)
    resp = http.post(os.environ["API_URL"] + "/predict", json=json.loads(raw))
    resp.raise_for_status()  # 422 or 5xx raises -> retry -> poison queue after 5 attempts
    result = resp.json()

    doc = {
        "id": item_id,
        "fileName": name,
        "etag": etag,
        "timestamp": started.isoformat(),
        "prediction": "churn" if result["churn"] else "no churn",
        "confidence": result["probability"],
        "modelVersion": result["model_version"],
        "durationMs": result["duration_ms"],
    }
    blob_service().get_blob_client("output", item_id + ".json").upload_blob(
        json.dumps({**doc, "input": json.loads(raw)}, indent=2), overwrite=True
    )
    container = cosmos_container()
    if container is not None:
        container.upsert_item(doc)  # upsert = safe to replay
    logger.info("DONE %s -> %s (%.4f)", name, doc["prediction"], doc["confidence"])


@app.function_name("recent")
@app.route(route="recent", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def recent(req: func.HttpRequest) -> func.HttpResponse:
    container = cosmos_container()
    items = []
    if container is not None:
        items = list(container.query_items(
            "SELECT TOP 20 c.id, c.fileName, c.timestamp, c.prediction, c.confidence, "
            "c.modelVersion, c.durationMs FROM c ORDER BY c.timestamp DESC",
            enable_cross_partition_query=True,
        ))
    return func.HttpResponse(
        json.dumps(items), mimetype="application/json", headers={"Cache-Control": "no-store"}
    )
