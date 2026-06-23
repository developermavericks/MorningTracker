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

# Check Redis connectivity to fall back to SQLite locally
redis_offline = False
if "localhost" in REDIS_URL or "127.0.0.1" in REDIS_URL or not REDIS_URL:
    try:
        import redis
        r = redis.from_url(REDIS_URL or "redis://localhost:6379/0", socket_timeout=2)
        r.ping()
    except Exception:
        redis_offline = True

if redis_offline:
    # Use SQLite for Celery Broker & Backend in local mode
    db_dir = os.path.dirname(os.path.abspath(__file__))
    broker_url = f"sqla+sqlite:///{os.path.join(db_dir, 'news_scraper.db')}"
    backend_url = f"db+sqlite:///{os.path.join(db_dir, 'news_scraper.db')}"
    print("Celery WARNING: Redis is offline. Falling back to local SQLite broker & backend.")
else:
    broker_url = REDIS_URL
    backend_url = REDIS_URL

app = Celery(
    "nexus_tasks",
    broker=broker_url,
    backend=backend_url
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_soft_time_limit=60 * 60,   # 60 minutes
    task_time_limit=90 * 60,        # 90 minutes
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
        "scraper.tasks.run_client_report_task": {"queue": "celery"},
        "scraper.tasks.check_client_schedules": {"queue": "celery"},
    },
    beat_schedule={
        "complete-stale-jobs-every-5-min": {
            "task": "scraper.tasks.complete_stale_jobs",
            "schedule": 5 * 60,  # Every 5 minutes
        },
        "check-client-schedules-every-5-min": {
            "task": "scraper.tasks.check_client_schedules",
            "schedule": 5 * 60,  # Every 5 minutes
        },
    }
)

# Break circular import by discovering tasks after app is defined
# We use the full task name to be safer
app.autodiscover_tasks(['scraper'], related_name='tasks')