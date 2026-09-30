from fastapi.testclient import TestClient
from jc.main import app


def test_health_and_info():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["success"]
        assert health.json()["request_id"] == health.headers["X-Request-ID"]
        assert client.get("/api/v1/system/info").json()["data"]["phase"] == "0–3"
