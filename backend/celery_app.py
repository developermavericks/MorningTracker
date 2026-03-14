import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "nexus_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["scraper.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_soft_time_limit=25 * 60,  # 25 minutes
    task_time_limit=30 * 60,       # 30 minutes
    worker_concurrency=2,          # Limit to 2 concurrent scrapes to save RAM
    worker_prefetch_multiplier=1,  # Prevent workers from grabbing too many heavy tasks
    task_acks_late=True,           # Task is acknowledged AFTER execution, ensuring it can be retried if worker dies
    task_reject_on_worker_lost=True, # Reject task if worker process is killed
)
