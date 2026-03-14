import pytest
from fastapi.testclient import TestClient
from main import app
from routers.auth_utils import create_access_token

client = TestClient(app)

@pytest.fixture
def auth_header():
    token = create_access_token({"sub": "tester@nexus.ai", "user_id": "user_test_999"})
    return {"Authorization": f"Bearer {token}"}

def test_01_empty_brands(auth_header):
    response = client.get("/api/brands/", headers=auth_header)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_02_add_and_remove_brand(auth_header):
    # Add
    res = client.post("/api/brands/", headers=auth_header, json={"name": "NVIDIA"})
    assert res.status_code == 200
    
    # Verify
    res = client.get("/api/brands/", headers=auth_header)
    names = [b["name"] for b in res.json()]
    assert "NVIDIA" in names
    
    # Delete
    res = client.delete("/api/brands/NVIDIA", headers=auth_header)
    assert res.status_code == 200

def test_03_brand_article_counts(auth_header):
    # This checks if the subquery for article counts works
    res = client.get("/api/brands/", headers=auth_header)
    assert res.status_code == 200
    for brand in res.json():
        assert "article_count" in brand
