# ---- Stage 1: build the virtualenv with pinned dependencies ----
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /build
COPY api/requirements.txt .
RUN pip install --no-compile -r requirements.txt \
 && find /opt/venv -type d \( -name tests -o -name test -o -name __pycache__ \) -prune -exec rm -rf {} + \
 && rm -rf /opt/venv/lib/python3.12/site-packages/pip /opt/venv/bin/pip*

# ---- Stage 2: slim runtime, non-root ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    MODEL_PATH=/app/model-1.0.0.joblib
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY api/main.py .
COPY model/model-1.0.0.joblib .
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
