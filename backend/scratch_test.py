import os
import sys
from datetime import datetime, date

# Set environment variables for the test
os.environ["ADMIN_EMAIL"] = "admin@test.com"
os.environ["ADMIN_PASSWORD"] = "admin_pass_123"

# Add backend to python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_dir)

from db.database import get_db_sync, Client, ClientSection, ClientKeyword, ClientRecipient, ClientRunLog
from sqlalchemy import select

def print_db_state():
    print("--- DB State Check ---")
    with get_db_sync() as db:
        clients = db.execute(select(Client)).scalars().all()
        print(f"Total Clients: {len(clients)}")
        for c in clients:
            print(f"Client: ID={c.id}, Name={c.name}, Schedule={c.scheduled_time}, Active={c.is_active}, Template={c.template_path}")
            sections = db.execute(select(ClientSection).where(ClientSection.client_id == c.id)).scalars().all()
            for s in sections:
                kwd_objs = db.execute(select(ClientKeyword).where(ClientKeyword.section_id == s.id)).scalars().all()
                kws = [k.keyword for k in kwd_objs]
                print(f"  Section: '{s.name}' with keywords {kws}")
            recipients = db.execute(select(ClientRecipient).where(ClientRecipient.client_id == c.id)).scalars().all()
            emails = [r.email for r in recipients]
            print(f"  Recipients: {emails}")

def trigger_sync_run(client_id):
    print(f"\n--- Triggering Synchronous Report Task for Client ID {client_id} ---")
    from scraper.tasks import run_client_report_task
    # Call the function synchronously
    res = run_client_report_task(client_id)
    print(f"Task result: {res}")
    
    # Check logs
    with get_db_sync() as db:
        logs = db.execute(
            select(ClientRunLog)
            .where(ClientRunLog.client_id == client_id)
            .order_by(ClientRunLog.started_at.desc())
            .limit(3)
        ).scalars().all()
        print("\nLast 3 Run Logs:")
        for log in logs:
            print(f"Log: ID={log.id}, Status={log.status}, Started={log.started_at}, Completed={log.completed_at}, Error={log.error_message}")

if __name__ == "__main__":
    print_db_state()
    # Trigger run for the first client
    trigger_sync_run(1)
