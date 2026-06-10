import smtplib
import os
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

logger = logging.getLogger(__name__)

def send_report_email(recipient_emails: list, client_name: str, docx_path: str, google_doc_url: str = None) -> bool:
    """
    Sends the generated DOCX report to the specified email addresses.
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
        body = (
            f"Hello Team,\n\n"
            f"Please find attached the daily news monitoring briefing for {client_name} generated on {date_str}.\n\n"
        )
        if google_doc_url:
            body += f"📝 Google Doc link (for online viewing & collaboration):\n{google_doc_url}\n\n"
            
        body += (
            f"Best regards,\n"
            f"NEXUS Global News Intelligence"
        )
        msg.attach(MIMEText(body, 'plain'))
        
        # Attach the report file
        filename = os.path.basename(docx_path)
        with open(docx_path, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={filename}")
            msg.attach(part)
            
        # Connect to SMTP server and send email
        port = int(smtp_port)
        if port == 465:
            # SSL Connection
            with smtplib.SMTP_SSL(smtp_host, port) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(sender_email, recipient_emails, msg.as_string())
        else:
            # TLS/StartTLS Connection
            with smtplib.SMTP(smtp_host, port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(sender_email, recipient_emails, msg.as_string())
                
        logger.info(f"Successfully sent report email for {client_name} to {recipient_emails}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send report email for {client_name}: {e}")
        return False
