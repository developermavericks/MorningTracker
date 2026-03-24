import os
import asyncio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from datetime import date, datetime

# Global setup
os.environ["ADMIN_EMAIL"] = "admin@test.com"
os.environ["ADMIN_PASSWORD"] = "admin_pass_123"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from main import app
from db.database import Base, User, ScrapeJob, Article, get_db_yield, init_db
from routers.auth_utils import create_access_token, get_password_hash

# Test DB setup
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
    
    # Seed data
    async with AsyncSessionTesting() as db:
        # Create Admin
        admin_user = User(id="admin_id", email="admin@test.com", password=get_password_hash("admin_pass_123"), name="Admin", is_admin=True)
        # Create User 1
        user1 = User(id="user1_id", email="user1@test.com", password=get_password_hash("pass1"), name="User 1", is_admin=False)
        # Create User 2
        user2 = User(id="user2_id", email="user2@test.com", password=get_password_hash("pass2"), name="User 2", is_admin=False)
        
        db.add_all([admin_user, user1, user2])
        await db.commit()
        
        # Create Job for User 1
        job1 = ScrapeJob(id="job1_id", user_id="user1_id", sector="tech", region="global", status="completed", started_at=datetime.now())
        # Create Job for User 2
        job2 = ScrapeJob(id="job2_id", user_id="user2_id", sector="finance", region="global", status="completed", started_at=datetime.now())
        db.add_all([job1, job2])
        await db.commit()
        
        # Create Article for User 1
        art1 = Article(id=1, user_id="user1_id", scrape_job_id="job1_id", title="Tech News", sector="tech", region="global")
        # Create Article for User 2
        art2 = Article(id=2, user_id="user2_id", scrape_job_id="job2_id", title="Finance News", sector="finance", region="global")
        db.add_all([art1, art2])
        await db.commit()

    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

def get_token(email, user_id, is_admin):
    return create_access_token({"sub": email, "user_id": user_id, "is_admin": is_admin})

def test_user_job_visibility():
    """Verify regular user only sees their own jobs."""
    token = get_token("user1@test.com", "user1_id", False)
    res = client.get("/api/scrape/jobs", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    jobs = res.json()
    assert len(jobs) == 1
    assert jobs[0]["id"] == "job1_id"
    assert "user_name" in jobs[0]
    assert "user_email" in jobs[0]
    assert jobs[0]["user_name"] == "User 1"

def test_admin_job_visibility():
    """Verify admin sees ALL jobs."""
    token = get_token("admin@test.com", "admin_id", True)
    res = client.get("/api/scrape/jobs", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    jobs = res.json()
    assert len(jobs) == 2
    ids = [j["id"] for j in jobs]
    assert "job1_id" in ids
    assert "job2_id" in ids

def test_user_article_visibility():
    """Verify regular user only sees their own articles."""
    token = get_token("user1@test.com", "user1_id", False)
    res = client.get("/api/articles/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["articles"][0]["id"] == 1

def test_admin_article_visibility():
    """Verify admin sees ALL articles."""
    token = get_token("admin@test.com", "admin_id", True)
    res = client.get("/api/articles/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    # If it works, it should return both articles
    assert data["total"] == 2
    ids = [a["id"] for a in data["articles"]]
    assert 1 in ids
    assert 2 in ids

def test_admin_stats_visibility():
    """Verify admin stats include all users."""
    token = get_token("admin@test.com", "admin_id", True)
    res = client.get("/api/articles/stats/summary", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    stats = res.json()
    assert stats["total_articles"] == 2
    # Jobs by status should also include both
    assert stats["jobs_by_status"][0]["count"] == 2

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
