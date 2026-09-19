"""HTTP endpoint that starts the daily_image Cloud Run Job on demand."""

import hmac
import logging
import os

import google.auth
from flask import Flask, jsonify, request
from google.auth.transport.requests import AuthorizedSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("daily_image_trigger")

PROJECT_ID = os.environ["PROJECT_ID"]
REGION = os.environ["REGION"]
JOB_NAME = os.environ["JOB_NAME"]
TRIGGER_TOKEN = os.environ["TRIGGER_TOKEN"]
if not TRIGGER_TOKEN:
    raise RuntimeError("TRIGGER_TOKEN must not be empty")

RUN_URL = (
    f"https://run.googleapis.com/v2/projects/{PROJECT_ID}"
    f"/locations/{REGION}/jobs/{JOB_NAME}:run"
)

app = Flask(__name__)


@app.post("/run")
def run_job():
    supplied = request.headers.get("Authorization", "")
    if not hmac.compare_digest(supplied.encode(), f"Bearer {TRIGGER_TOKEN}".encode()):
        return jsonify(error="unauthorized"), 401

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    resp = AuthorizedSession(credentials).post(RUN_URL, json={}, timeout=30)
    if not resp.ok:
        logger.error("Job run request failed: %s %s", resp.status_code, resp.text)
        return jsonify(error="failed to start job"), 502

    logger.info("Started %s", JOB_NAME)
    return jsonify(status="started"), 202
