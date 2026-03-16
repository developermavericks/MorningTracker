# MUST BE THE FIRST IMPORTS if using gevent in workers
import os
import sys
import warnings

# Ensure current directory is in sys.path for robust imports on Railway
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Suppress MonkeyPatchWarning as we manually handle the order
try:
    from gevent import monkey
    warnings.filterwarnings("ignore", message="Monkey-patching ssl after ssl has already been imported")
except ImportError:
    pass

if os.environ.get("CELERY_WORKER_GEVENT") == "1":
    from gevent import monkey
    monkey.patch_all()
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "nexus_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_soft_time_limit=25 * 60,   # 25 minutes
    task_time_limit=30 * 60,        # 30 minutes
    # Note: With prefork, concurrency refers to child processes.
    worker_concurrency=int(os.getenv("CELERY_WORKER_CONCURRENCY", "8")), 
    worker_prefetch_multiplier=10,   
    task_acks_late=True,           
    task_reject_on_worker_lost=True, 
    task_routes={
        "scraper.tasks.run_scrape_task": {"queue": "celery"},
        "scraper.tasks.scrape_article_node": {"queue": "celery"},
        "scraper.tasks.enrich_article_node": {"queue": "celery"},
        "scraper.tasks.complete_stale_jobs": {"queue": "celery"},
    },
    beat_schedule={
        "complete-stale-jobs-every-5-min": {
            "task": "scraper.tasks.complete_stale_jobs",
            "schedule": 5 * 60,  # Every 5 minutes
        },
    }
)

# Break circular import by discovering tasks after app is defined
# We use the full task name to be safer
app.autodiscover_tasks(['scraper'], related_name='tasks')