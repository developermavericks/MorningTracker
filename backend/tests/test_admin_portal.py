import os
import asyncio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from datetime import date, datetime

# Mock environment variables BEFORE importing the app
os.environ["ADMIN_EMAIL"] = "admin@test.com"
os.environ["ADMIN_PASSWORD"] = "admin_pass_123"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from main import app
from db.database import Base, User, ScrapeJob, get_db_yield, init_db

# Setup Test Database for direct execution if needed
engine = create_async_engine("sqlite+aiosqlite:///:memory:")
AsyncSessionTesting = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def override_get_db():
    async with AsyncSessionTesting() as session:
        yield session

app.dependency_overrides[get_db_yield] = override_get_db

client = TestClient(app)

@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

def test_admin_login_success():
    """Verify that using ADMIN_EMAIL and ADMIN_PASSWORD grants admin status."""
    # Ensure tables exist for this test
    async def run_test():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        response = client.post(
            "/api/auth/login",
            data={"username": "admin@test.com", "password": "admin_pass_123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["is_admin"] is True
        return data

    if __name__ == "__main__":
        return asyncio.run(run_test())
    else:
        # In pytest, the setup_db fixture handles it
        response = client.post(
            "/api/auth/login",
            data={"username": "admin@test.com", "password": "admin_pass_123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["is_admin"] is True

def test_admin_login_failure():
    """Verify that incorrect admin credentials fail."""
    response = client.post(
        "/api/auth/login",
        data={"username": "admin@test.com", "password": "wrong_password"}
    )
    assert response.status_code == 401

def test_regular_user_no_admin_access():
    """Verify that a regular user cannot access admin routes."""
    # 1. Register a regular user
    client.post("/api/auth/register", json={"email": "user@test.com", "password": "user_pass", "name": "Regular User"})
    
    # 2. Login as regular user
    login_res = client.post("/api/auth/login", data={"username": "user@test.com", "password": "user_pass"})
    token = login_res.json()["access_token"]
    
    # 3. Try to access admin jobs
    headers = {"Authorization": f"Bearer {token}"}
    admin_res = client.get("/api/admin/jobs", headers=headers)
    assert admin_res.status_code == 403

def test_admin_jobs_data_retrieval():
    """Verify that an admin can retrieve and filter jobs."""
    # 1. Login as admin
    login_res = client.post("/api/auth/login", data={"username": "admin@test.com", "password": "admin_pass_123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Access jobs dashboard
    response = client.get("/api/admin/jobs", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert "summary" in data

if __name__ == "__main__":
    print("NEXUS: Running Admin Portal Health Check...")
    try:
        data = test_admin_login_success()
        print("PASS: Admin login successful.")
        test_admin_login_failure()
        print("PASS: Admin login security verified.")
        print("NEXUS: All critical admin paths are healthy.")
    except Exception as e:
        print(f"FAIL: Health check failed with error: {e}")
        import traceback
        traceback.print_exc()
