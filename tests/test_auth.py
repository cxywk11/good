from jc.models import User
from sqlalchemy import select


def test_auth_rotation_logout_and_roles(client, sessions):
    credentials = {"email": "user@example.com", "password": "strong-test-password"}
    assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
    assert client.post("/api/v1/auth/register", json=credentials).status_code == 409
    token = client.post("/api/v1/auth/login", json=credentials).json()["data"]
    headers = {"Authorization": "Bearer " + token["access_token"]}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.get("/api/v1/admin/mappings", headers=headers).status_code == 403
    with sessions() as db:
        user = db.scalar(select(User))
        user.role = "ADMIN"
        db.commit()
    assert client.get("/api/v1/admin/mappings", headers=headers).status_code == 200
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": token["refresh_token"]})
    assert rotated.status_code == 200
    assert (
        client.post("/api/v1/auth/refresh", json={"refresh_token": token["refresh_token"]}).status_code == 401
    )
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    token = client.post("/api/v1/auth/login", json=credentials).json()["data"]
    headers = {"Authorization": "Bearer " + token["access_token"]}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
