import os
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents'
]

def get_drive_service():
    """Initializes the Google Drive API service using local credentials JSON."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    creds_path = os.path.join(base_dir, "google_credentials.json")
    
    if not os.path.exists(creds_path):
        logger.warning(f"Google credentials file not found at {creds_path}. Skipping Google Docs integration.")
        return None
        
    try:
        creds = service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"Failed to initialize Google Drive service: {e}")
        return None

def get_or_create_reports_folder(service, client_name: str) -> str:
    """Finds or creates a client-specific reports folder in Google Drive."""
    try:
        # Check if the folder already exists
        query = f"name = 'Morning Tracker - {client_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = results.get('files', [])
        
        if files:
            return files[0]['id']
            
        # Create folder if it doesn't exist
        folder_metadata = {
            'name': f'Morning Tracker - {client_name}',
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = service.files().create(body=folder_metadata, fields='id').execute()
        logger.info(f"Created new Google Drive folder: Morning Tracker - {client_name} (ID: {folder['id']})")
        return folder['id']
    except Exception as e:
        logger.error(f"Error getting/creating Google Drive folder: {e}")
        return None

def upload_docx_to_google_doc(docx_path: str, client_name: str, date_str: str, recipients: list) -> str:
    """
    Uploads a local DOCX file to Google Drive and converts it to a native Google Doc.
    Shares the generated Google Doc with the list of recipient email addresses.
    Returns the URL link of the Google Doc.
    """
    service = get_drive_service()
    if not service:
        return None
        
    try:
        # Get target folder
        folder_id = get_or_create_reports_folder(service, client_name)
        
        file_name = f"{client_name} Briefing - {date_str}"
        
        # Metadata configuration to automatically convert DOCX to Google Docs
        file_metadata = {
            'name': file_name,
            'mimeType': 'application/vnd.google-apps.document'  # Converts to Google Docs format
        }
        
        if folder_id:
            file_metadata['parents'] = [folder_id]
            
        media = MediaFileUpload(
            docx_path, 
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
            resumable=True
        )
        
        # Create/Upload the file
        uploaded_file = service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id, webViewLink'
        ).execute()
        
        doc_id = uploaded_file.get('id')
        web_link = uploaded_file.get('webViewLink')
        
        logger.info(f"Successfully uploaded and converted report to Google Doc ID: {doc_id}")
        
        # Share document with recipient emails
        for email in recipients:
            if not email:
                continue
            try:
                user_permission = {
                    'type': 'user',
                    'role': 'writer',  # Grant Editor access to organization members
                    'emailAddress': email
                }
                service.permissions().create(
                    fileId=doc_id, 
                    body=user_permission, 
                    sendNotificationEmails=False
                ).execute()
                logger.info(f"Shared Google Doc {doc_id} with {email}")
            except Exception as share_err:
                logger.error(f"Failed to share Google Doc with {email}: {share_err}")
                
        return web_link
        
    except Exception as e:
        logger.error(f"Failed to upload report to Google Docs: {e}", exc_info=True)
        return None
