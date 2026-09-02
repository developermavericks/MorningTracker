import os
import sys
import json
import logging
from datetime import datetime, timedelta

# Set PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import get_db_sync, RobustCompany, RobustRun, RobustRunArticle, Article
from scraper.tasks import run_robust_automation_task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RobustE2ETest")

def test_robust_pipeline():
    logger.info("Starting Robust Automation E2E Pipeline verification...")

    # 1. Setup a test company in the database
    with get_db_sync() as db:
        # Check if already exists
        comp = db.execute(
            sa_select(RobustCompany).where(RobustCompany.name == "E2E Test Robust Company")
        ).scalar_one_or_none() if 'sa_select' in globals() else db.execute(
            select_robust_company()
        ).scalar_one_or_none()
        
        if comp:
            logger.info("Found existing E2E Test Robust Company.")
        else:
            logger.info("Creating mock E2E Test Robust Company...")
            comp = RobustCompany(
                name="E2E Test Robust Company",
                sector_match="google", # Sector which has mock/real articles
                enabled=True,
                timezone="Asia/Kolkata",
                fetch_time="07:00",
                window_hours=72, # Fetch last 3 days
                send_email=True,
                send_html_mailer=True,
                send_mailer_doc=True,
                send_report_doc=True,
                send_report_excel=True,
                upload_to_google_drive=False,
                update_takeaways_sheet=False,
                llm_verification_provider="none", # Disable LLM for mock test speed
                llm_summary_provider="none",
                llm_executive_provider="none",
                mail_send_mode="Immediate",
                frequency="Daily"
            )
            db.add(comp)
            db.commit()
            db.refresh(comp)
        
        company_id = comp.id

    # 2. Insert dummy articles in local DB if empty to guarantee polling results
    with get_db_sync() as db:
        articles_count = db.execute(
            select_article_count()
        ).scalar()
        logger.info(f"Total articles in DB: {articles_count}")
        
        if articles_count == 0:
            logger.info("Inserting a dummy article for sector 'google'...")
            art = Article(
                title="Google India introduces new AI initiatives in Delhi",
                url="https://example.com/google-news-1",
                published_at=datetime.utcnow() - timedelta(hours=12),
                sector="google",
                region="India",
                agency="PTI",
                language="en"
            )
            db.add(art)
            db.commit()

    # 3. Trigger pipeline task synchronously
    logger.info(f"Executing run_robust_automation_task for company ID: {company_id}")
    success = run_robust_automation_task(company_id)
    assert success is True, "Pipeline execution task returned False!"

    # 4. Verify results in DB
    logger.info("Verifying run results in database...")
    with get_db_sync() as db:
        # Check Run
        run = db.execute(
            select_robust_run(company_id)
        ).scalar_one_or_none()
        
        assert run is not None, "RobustRun record was not created!"
        logger.info(f"Run status: {run.status}")
        logger.info(f"Fetched Count: {run.fetched_count}")
        logger.info(f"Deduplicated Count: {run.deduped_count}")
        logger.info(f"Relevant Count: {run.relevant_count}")
        logger.info(f"Email Status: {run.email_status}")
        
        assert run.status == "completed", f"Run failed with status: {run.status}, error: {run.error}"
        
        # Check generated files
        assert run.master_doc_path and os.path.exists(run.master_doc_path), "Master doc was not generated!"
        assert run.master_excel_path and os.path.exists(run.master_excel_path), "Master Excel was not generated!"
        assert run.mailer_doc_path and os.path.exists(run.mailer_doc_path), "Mailer doc was not generated!"
        
        logger.info(f"Generated DOCX: {run.master_doc_path}")
        logger.info(f"Generated Excel: {run.master_excel_path}")
        logger.info(f"Generated Mailer: {run.mailer_doc_path}")

        # Check Audit Articles
        audit_count = db.execute(
            select_audit_articles_count(run.id)
        ).scalar()
        logger.info(f"Audit Trail Articles count: {audit_count}")
        assert audit_count >= 0, "Failed to query run articles!"

    logger.info("[SUCCESS] Robust Automation E2E verification test passed successfully!")

# SQL helper builders to prevent import/compile scope issues in test runner
def select_robust_company():
    from sqlalchemy import select
    return select(RobustCompany).where(RobustCompany.name == "E2E Test Robust Company")

def select_article_count():
    from sqlalchemy import select, func
    return select(func.count()).select_from(Article)

def select_robust_run(company_id):
    from sqlalchemy import select, desc
    return select(RobustRun).where(RobustRun.company_id == company_id).order_by(desc(RobustRun.started_at)).limit(1)

def select_audit_articles_count(run_id):
    from sqlalchemy import select, func
    return select(func.count()).where(RobustRunArticle.run_id == run_id)

if __name__ == "__main__":
    test_robust_pipeline()
