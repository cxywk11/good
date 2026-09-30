from fastapi.testclient import TestClient
from jc.db import get_db
from jc.main import app


def test_empty_matches_api(sessions):
    def database():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/matches/today")
            assert response.json()["data"]["items"] == []
            assert response.json()["data"]["demo_mode"] is True
            assert client.get("/api/v1/matches/today?page_size=1000").status_code == 422
    finally:
        app.dependency_overrides.clear()
