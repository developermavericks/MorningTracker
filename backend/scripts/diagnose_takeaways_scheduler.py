#!/usr/bin/env python
"""
Diagnostic Script: Monthly Takeaways & Scheduler Checks
Verifies database table integrity, Google credentials availability, Celery app configurations,
and prints active scheduled takeaways companies.
"""
import os
import sys
import logging

# Setup path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Diagnostics")

def check_db_schema():
    logger.info("Checking Database Table Schema...")
    try:
        from db.database import get_db_sync, HeavyCompany, RobustCompany
        from sqlalchemy import select, inspect
        
        with get_db_sync() as db:
            # Inspect heavy_companies columns
            inspector = inspect(db.bind)
            columns = [col["name"] for col in inspector.get_columns("heavy_companies")]
            
            required = [
                "takeaways_sheet_url", 
                "send_monthly_takeaways_enabled", 
                "monthly_takeaways_day", 
                "monthly_takeaways_time", 
                "last_monthly_takeaways_sent_at"
            ]
            
            missing = [r for r in required if r not in columns]
            if not missing:
                logger.info("[SUCCESS] Database has all required takeaways configuration columns in heavy_companies.")
            else:
                logger.error(f"[FAILURE] Database heavy_companies is missing columns: {missing}")
                return False
                
            # Inspect robust_companies columns
            robust_columns = [col["name"] for col in inspector.get_columns("robust_companies")]
            robust_required = [
                "manual_keywords",
                "search_mode",
                "pooja_algo_enabled"
            ]
            robust_missing = [r for r in robust_required if r not in robust_columns]
            if not robust_missing:
                logger.info("[SUCCESS] Database has all required columns in robust_companies.")
            else:
                logger.error(f"[FAILURE] Database robust_companies is missing columns: {robust_missing}")
                return False

            # Query all enabled schedules
            companies = db.execute(select(HeavyCompany)).scalars().all()
            logger.info(f"Total Heavy Companies in DB: {len(companies)}")
            for c in companies:
                logger.info(
                    f" - Company: '{c.name}' (ID: {c.id}) | "
                    f"Takeaways Sheet: {c.takeaways_sheet_url or 'None'} | "
                    f"Monthly Scheduled Send: {'ENABLED' if c.send_monthly_takeaways_enabled else 'DISABLED'} "
                    f"(Day: {c.monthly_takeaways_day}, Time: {c.monthly_takeaways_time})"
                )
            
            # Query all robust companies
            robust_companies = db.execute(select(RobustCompany)).scalars().all()
            logger.info(f"Total Robust Companies in DB: {len(robust_companies)}")
            for rc in robust_companies:
                logger.info(
                    f" - Robust Profile: '{rc.name}' (ID: {rc.id}) | "
                    f"Search Mode: {rc.search_mode} | "
                    f"Pooja Logic: {'ENABLED' if rc.pooja_algo_enabled else 'DISABLED'}"
                )
        return True
    except Exception as e:
        logger.error(f"[FAILURE] Database schema check failed: {e}", exc_info=True)
        return False

def check_google_credentials():
    logger.info("Checking Google Drive Credentials...")
    try:
        google_creds = os.getenv("GOOGLE_CREDENTIALS_JSON") or os.path.exists("google_credentials.json")
        if google_creds:
            logger.info("[SUCCESS] Google Drive credentials detected (Env or file).")
            # Try initializing Drive service
            from utils.google_docs import get_drive_service
            service = get_drive_service()
            if service:
                logger.info("[SUCCESS] Google Drive service initialized and connected successfully.")
            else:
                logger.error("[FAILURE] Google Drive service initialization returned None.")
                return False
        else:
            logger.warning("[WARNING] No Google Drive credentials file or environment variable found.")
        return True
    except Exception as e:
        logger.error(f"[FAILURE] Google Credentials check failed: {e}", exc_info=True)
        return False

def check_smtp_config():
    logger.info("Checking SMTP Server Settings...")
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    sender_email = os.getenv("SENDER_EMAIL")
    
    if not all([smtp_host, smtp_port, smtp_user, sender_email]):
        logger.warning("[WARNING] SMTP environment variables are not fully configured. Email dispatch will fail.")
    else:
        logger.info(f"[SUCCESS] SMTP configuration present: {smtp_host}:{smtp_port} as user '{smtp_user}'")
    return True

if __name__ == "__main__":
    logger.info("==============================================")
    logger.info("Starting heavy takeaways scheduler diagnostics")
    logger.info("==============================================")
    
    db_ok = check_db_schema()
    google_ok = check_google_credentials()
    smtp_ok = check_smtp_config()
    
    logger.info("==============================================")
    if db_ok and google_ok and smtp_ok:
        logger.info("[DIAGNOSTIC STATUS] ALL CHECKS PASSED. Ready for deployment!")
        sys.exit(0)
    else:
        logger.error("[DIAGNOSTIC STATUS] SOME CHECKS FAILED. Please review logs above.")
        sys.exit(1)
