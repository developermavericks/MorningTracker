import smtplib
import os
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

logger = logging.getLogger(__name__)

def send_report_email(recipient_emails: list, client_name: str, docx_path_filtered: str, docx_path_master: str, google_doc_url_filtered: str = None, google_doc_url_master: str = None, has_articles: bool = True, brief_content: str = None, excel_path_filtered: str = None, excel_path_master: str = None, html_body: str = None, cumulative_sheet_url: str = None) -> bool:
    """
    Sends the generated DOCX and Excel reports (Filtered and Master) and the executive brief to the specified email addresses.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SENDER_EMAIL")
    
    # Check if configurations are present
    if not all([smtp_host, smtp_port, smtp_user, smtp_password, sender_email]):
        logger.error("SMTP environment variables are not fully configured. Cannot send email.")
        return False
        
    try:
        # Create the email message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ", ".join(recipient_emails)
        date_str = datetime.now().strftime("%B %d, %Y")
        msg['Subject'] = f"Daily News Briefing: {client_name} - {date_str}"
        
        # Email Body
        body = f"Hello Team,\n\n"
        
        if brief_content:
            body += (
                f"📰 DAILY BRIEF SUMMARY:\n"
                f"--------------------------------------------------\n"
                f"{brief_content}\n"
                f"--------------------------------------------------\n\n"
            )
            
        if docx_path_filtered or docx_path_master or excel_path_filtered or excel_path_master:
            body += f"Please find attached the daily news monitoring briefings (Word and Excel formats) for {client_name} generated on {date_str}.\n\n"
        
        if google_doc_url_filtered:
            label = "Mailer Google Doc" if "google" in client_name.lower() else "Filtered Report (Relevant Articles Only)"
            body += f"📝 {label}:\n{google_doc_url_filtered}\n\n"
        if google_doc_url_master:
            label = "Master Report Google Doc" if "google" in client_name.lower() else "Master Report (All Search Matches)"
            body += f"📝 {label}:\n{google_doc_url_master}\n\n"
        if cumulative_sheet_url:
            body += f"📈 Cumulative Google Sheet (All Filtered Articles by Date):\n{cumulative_sheet_url}\n\n"
            
        body += (
            f"Best regards,\n"
            f"NEXUS Global News Intelligence"
        )
        if html_body:
            msg.attach(MIMEText(html_body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
        
        # Attach the Filtered report file
        if docx_path_filtered and os.path.exists(docx_path_filtered):
            filename_f = os.path.basename(docx_path_filtered)
            with open(docx_path_filtered, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={filename_f}")
                msg.attach(part)
                
        # Attach the Master report file
        if docx_path_master and os.path.exists(docx_path_master):
            filename_m = os.path.basename(docx_path_master)
            with open(docx_path_master, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={filename_m}")
                msg.attach(part)

        # Attach the Filtered Excel report file
        if excel_path_filtered and os.path.exists(excel_path_filtered):
            filename_ef = os.path.basename(excel_path_filtered)
            with open(excel_path_filtered, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={filename_ef}")
                msg.attach(part)
                
        # Attach the Master Excel report file
        if excel_path_master and os.path.exists(excel_path_master):
            filename_em = os.path.basename(excel_path_master)
            with open(excel_path_master, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={filename_em}")
                msg.attach(part)
            
        # Connect to SMTP server and send email with retries and timeouts
        port = int(smtp_port)
        max_attempts = 3
        attempt = 0
        success = False
        last_error = None
        
        import time
        
        while attempt < max_attempts and not success:
            attempt += 1
            try:
                if port == 465:
                    # SSL Connection
                    with smtplib.SMTP_SSL(smtp_host, port, timeout=30) as server:
                        server.login(smtp_user, smtp_password)
                        server.sendmail(sender_email, recipient_emails, msg.as_string())
                else:
                    # TLS/StartTLS Connection
                    with smtplib.SMTP(smtp_host, port, timeout=30) as server:
                        server.starttls()
                        server.login(smtp_user, smtp_password)
                        server.sendmail(sender_email, recipient_emails, msg.as_string())
                success = True
            except Exception as smtp_err:
                last_error = smtp_err
                logger.warning(f"SMTP attempt {attempt} failed for {client_name}: {smtp_err}")
                if attempt < max_attempts:
                    time.sleep(5)
                    
        if not success:
            raise last_error or Exception("SMTP send failed after all retries")
                
        logger.info(f"Successfully sent report email for {client_name} to {recipient_emails} (completed on attempt {attempt})")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send report email for {client_name}: {e}")
        return False

def send_error_alert_email(client_name: str, error_details: str) -> bool:
    """
    Sends an immediate fail-safe email alert with exact error details and timestamps if any part of the pipeline fails.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SENDER_EMAIL")
    # Fetch dynamic recipients from DB if available
    recipients = []
    try:
        from db.database import get_db_sync, SystemSetting
        from sqlalchemy import select
        import json
        with get_db_sync() as db:
            stmt = select(SystemSetting).where(SystemSetting.key == "fail_safe_recipients")
            res = db.execute(stmt)
            setting = res.scalar_one_or_none()
            if setting and setting.value:
                recipients = json.loads(setting.value)
    except Exception as db_err:
        logger.error(f"Failed to read fail_safe_recipients from DB, falling back: {db_err}")
        
    if not recipients:
        admin_email = os.getenv("ADMIN_EMAIL") or "admin@test.com"
        recipients = [
            admin_email,
            "divyanshsharma@themavericksindia.com",
            "pooja@themavericksindia.com",
            "satyam.singh@themavericksindia.com",
            "arunkumar@themavericksindia.com"
        ]
        
    # Deduplicate recipients
    recipients = list(set([r.strip() for r in recipients if r]))
    
    if not all([smtp_host, smtp_port, smtp_user, smtp_password, sender_email]):
        logger.error("SMTP environment variables are not fully configured. Cannot send error alert.")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ", ".join(recipients)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg['Subject'] = f"🚨 PIPELINE FAILURE ALERT: {client_name} - {timestamp}"
        
        body = (
            f"ALERT: The news gathering/reporting pipeline for client '{client_name}' failed.\n\n"
            f"Timestamp: {timestamp}\n"
            f"Error details:\n"
            f"----------------------------------------\n"
            f"{error_details}\n"
            f"----------------------------------------\n\n"
            f"Please investigate the worker logs and system health.\n"
        )
        msg.attach(MIMEText(body, 'plain'))
        
        port = int(smtp_port)
        if port == 465:
            with smtplib.SMTP_SSL(smtp_host, port, timeout=30) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(sender_email, recipients, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, port, timeout=30) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(sender_email, recipients, msg.as_string())
                
        logger.info(f"Successfully sent error alert email to {recipients} for {client_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to send error alert email for {client_name}: {e}")
        return False


def send_monthly_takeaways_report_email(recipient_emails: list, client_name: str, excel_path: str, google_sheet_url: str = None) -> bool:
    """
    Sends the monthly consolidated takeaways spreadsheet as an attachment
    and includes the Google Sheet web link in the email body.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SENDER_EMAIL")
    
    if not all([smtp_host, smtp_port, smtp_user, smtp_password, sender_email]):
        logger.error("SMTP environment variables are not fully configured. Cannot send monthly report.")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ", ".join(recipient_emails)
        
        last_month = datetime.now()
        date_str = last_month.strftime("%B %Y")
        msg['Subject'] = f"Monthly Strategic Takeaways Report: {client_name} - {date_str}"
        
        body = (
            f"Hello Team,\n\n"
            f"Please find attached the monthly strategic takeaways report for {client_name} (Excel format) for {date_str}.\n\n"
        )
        if google_sheet_url:
            body += f"📈 Strategic Takeaways Google Sheet (Historical Timeline):\n{google_sheet_url}\n\n"
            
        body += (
            f"Best regards,\n"
            f"THE MAVERICKS Intelligence Desk"
        )
        msg.attach(MIMEText(body, 'plain'))
        
        # Attach the Excel report file
        if excel_path and os.path.exists(excel_path):
            filename = os.path.basename(excel_path)
            with open(excel_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={filename}")
                msg.attach(part)
                
        port = int(smtp_port)
        if port == 465:
            with smtplib.SMTP_SSL(smtp_host, port, timeout=30) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(sender_email, recipient_emails, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, port, timeout=30) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(sender_email, recipient_emails, msg.as_string())
                
        logger.info(f"Successfully sent monthly takeaways report to {recipient_emails} for {client_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to send monthly takeaways report for {client_name}: {e}")
        return False

