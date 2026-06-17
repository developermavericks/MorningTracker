import os
import logging
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from docx import Document
from docx.shared import RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents'
]

def add_horizontal_line(paragraph):
    """Adds a thin bottom border to a paragraph (horizontal divider line)."""
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '6')  # Size 6 = 3/4 pt
    bottom.set(qn('w:space'), '12')
    bottom.set(qn('w:color'), 'D3D3D3')  # Light grey
    pBdr.append(bottom)
    pPr.append(pBdr)

def merge_docx_files(new_docx_path: str, existing_docx_path: str, output_path: str):
    """
    Combines two DOCX files.
    The new daily briefing is prepended at the top, followed by a divider, 
    and then the previous days' content from the existing monthly file.
    """
    # Read new briefing
    new_doc = Document(new_docx_path)
    # Read existing master doc
    existing_doc = Document(existing_docx_path)
    
    # Create combined document
    combined = Document()
    
    # Copy margins from new_doc
    for section in new_doc.sections:
        for comb_section in combined.sections:
            comb_section.top_margin = section.top_margin
            comb_section.bottom_margin = section.bottom_margin
            comb_section.left_margin = section.left_margin
            comb_section.right_margin = section.right_margin
            
    # 1. Copy paragraphs from new_doc (the new daily briefing)
    for paragraph in new_doc.paragraphs:
        new_p = combined.add_paragraph()
        if paragraph.style:
            try:
                new_p.style = paragraph.style
            except Exception:
                pass
        new_p.alignment = paragraph.alignment
        new_p.paragraph_format.space_before = paragraph.paragraph_format.space_before
        new_p.paragraph_format.space_after = paragraph.paragraph_format.space_after
        new_p.paragraph_format.line_spacing = paragraph.paragraph_format.line_spacing
        
        for run in paragraph.runs:
            new_run = new_p.add_run(run.text)
            new_run.bold = run.bold
            new_run.italic = run.italic
            new_run.underline = run.underline
            new_run.font.name = run.font.name
            new_run.font.size = run.font.size
            if run.font.color and run.font.color.rgb:
                new_run.font.color.rgb = run.font.color.rgb
            
        if paragraph._p.pPr is not None and paragraph._p.pPr.find(qn('w:pBdr')) is not None:
            add_horizontal_line(new_p)
            
    # Add page/spacer break
    sep_p = combined.add_paragraph()
    sep_run = sep_p.add_run("\n" + "="*40 + "\n")
    sep_run.font.color.rgb = RGBColor(180, 180, 180)
    sep_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # 2. Copy paragraphs from existing_doc (previous days)
    for paragraph in existing_doc.paragraphs:
        new_p = combined.add_paragraph()
        if paragraph.style:
            try:
                new_p.style = paragraph.style
            except Exception:
                pass
        new_p.alignment = paragraph.alignment
        new_p.paragraph_format.space_before = paragraph.paragraph_format.space_before
        new_p.paragraph_format.space_after = paragraph.paragraph_format.space_after
        new_p.paragraph_format.line_spacing = paragraph.paragraph_format.line_spacing
        
        for run in paragraph.runs:
            new_run = new_p.add_run(run.text)
            new_run.bold = run.bold
            new_run.italic = run.italic
            new_run.underline = run.underline
            new_run.font.name = run.font.name
            new_run.font.size = run.font.size
            if run.font.color and run.font.color.rgb:
                new_run.font.color.rgb = run.font.color.rgb
            
        if paragraph._p.pPr is not None and paragraph._p.pPr.find(qn('w:pBdr')) is not None:
            add_horizontal_line(new_p)
            
    combined.save(output_path)

def get_drive_service():
    """Initializes the Google Drive API service using environment variable or local credentials JSON."""
    import json
    
    # 1. Try to load credentials from environment variable first (best for Railway/production)
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        try:
            creds_json = creds_json.strip("'\"")
            creds_data = json.loads(creds_json)
            if "private_key" in creds_data:
                creds_data["private_key"] = creds_data["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(creds_data, scopes=SCOPES)
            return build('drive', 'v3', credentials=creds, cache_discovery=False)
        except Exception as e:
            logger.error(f"Failed to load Google credentials from environment variable: {e}")
            
    # 2. Fallback to local file (development)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    creds_path = os.path.join(base_dir, "google_credentials.json")
    
    if not os.path.exists(creds_path):
        logger.warning(f"Google credentials file not found at {creds_path} and no environment variable set. Skipping Google Docs integration.")
        return None
        
    try:
        creds = service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        return build('drive', 'v3', credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"Failed to initialize Google Drive service from file: {e}")
        return None

def get_or_create_reports_folder(service, client_name: str) -> str:
    """Finds or creates a client-specific reports folder in Google Drive."""
    try:
        parent_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        if parent_id:
            query = f"name = 'Morning Tracker - {client_name}' and mimeType = 'application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed = false"
        else:
            query = f"name = 'Morning Tracker - {client_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            
        results = service.files().list(
            q=query, 
            spaces='drive', 
            fields='files(id, name)',
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        files = results.get('files', [])
        
        if files:
            return files[0]['id']
            
        folder_metadata = {
            'name': f'Morning Tracker - {client_name}',
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            folder_metadata['parents'] = [parent_id]
            
        folder = service.files().create(
            body=folder_metadata, 
            fields='id',
            supportsAllDrives=True
        ).execute()
        logger.info(f"Created new Google Drive folder: Morning Tracker - {client_name} (ID: {folder['id']})")
        return folder['id']
    except Exception as e:
        logger.error(f"Error getting/creating Google Drive folder: {e}")
        return None

def upload_docx_to_google_doc(docx_path: str, client_name: str, date_str: str, recipients: list, doc_suffix: str = "") -> str:
    """
    Uploads a local DOCX file to Google Drive and converts it to a native Google Doc.
    Supports continuous daily appending into a single monthly document (e.g. Scapia - June 2026).
    Appends new reports at the top of the monthly Google Doc to align with outline-navigation.
    Shares the Google Doc with the list of recipient email addresses.
    Returns the URL link of the Google Doc.
    """
    service = get_drive_service()
    if not service:
        return None
        
    try:
        folder_id = get_or_create_reports_folder(service, client_name)
        
        # Build Monthly Document Name (e.g., "Scapia - June 2026")
        month_year_str = datetime.now().strftime("%B %Y")
        file_name = f"{client_name}{doc_suffix} - {month_year_str}"
        
        # Search for an existing monthly Google Doc inside the client's folder
        query = f"name = '{file_name}' and mimeType = 'application/vnd.google-apps.document' and '{folder_id}' in parents and trashed = false"
        results = service.files().list(
            q=query, 
            spaces='drive', 
            fields='files(id, webViewLink)',
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        files = results.get('files', [])
        
        doc_id = None
        web_link = None
        
        if files:
            # Monthly document already exists -> Export, Merge, and Update in-place
            doc_id = files[0]['id']
            web_link = files[0]['webViewLink']
            logger.info(f"Monthly document exists: ID {doc_id}. Initiating daily append merge...")
            
            temp_existing_path = docx_path + ".existing.docx"
            temp_combined_path = docx_path + ".combined.docx"
            
            media = None
            try:
                # 1. Export Google Doc as a local DOCX using downloader
                from googleapiclient.http import MediaIoBaseDownload
                import io
                
                export_request = service.files().export_media(
                    fileId=doc_id, 
                    mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, export_request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    
                with open(temp_existing_path, "wb") as f:
                    f.write(fh.getvalue())
                
                # 2. Merge new daily report with existing month report (new on top)
                merge_docx_files(docx_path, temp_existing_path, temp_combined_path)
                
                # 3. Update the existing Google Doc content
                media = MediaFileUpload(
                    temp_combined_path, 
                    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
                    resumable=True
                )
                service.files().update(
                    fileId=doc_id,
                    media_body=media,
                    supportsAllDrives=True
                ).execute()
                
                logger.info(f"Successfully appended report to monthly Google Doc: {file_name}")
                
            except Exception as merge_err:
                logger.error(f"Failed to merge with existing monthly doc: {merge_err}", exc_info=True)
            finally:
                # Safely release Windows file lock
                if media and hasattr(media, '_fd') and media._fd:
                    try: media._fd.close()
                    except: pass
                # Cleanup temp files
                if os.path.exists(temp_existing_path):
                    os.remove(temp_existing_path)
                if os.path.exists(temp_combined_path):
                    os.remove(temp_combined_path)
        
        if not doc_id:
            # Monthly document does not exist yet -> Create new
            logger.info(f"Creating new monthly Google Doc: {file_name}")
            file_metadata = {
                'name': file_name,
                'mimeType': 'application/vnd.google-apps.document'
            }
            if folder_id:
                file_metadata['parents'] = [folder_id]
                
            media = None
            try:
                media = MediaFileUpload(
                    docx_path, 
                    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
                    resumable=True
                )
                uploaded_file = service.files().create(
                    body=file_metadata, 
                    media_body=media, 
                    fields='id, webViewLink',
                    supportsAllDrives=True
                ).execute()
                
                doc_id = uploaded_file.get('id')
                web_link = uploaded_file.get('webViewLink')
                logger.info(f"Created monthly Google Doc ID: {doc_id}")
            finally:
                if media and hasattr(media, '_fd') and media._fd:
                    try: media._fd.close()
                    except: pass
            
        # Share document with recipient emails (always run to ensure new recipients get access)
        for email in recipients:
            if not email:
                continue
            try:
                user_permission = {
                    'type': 'user',
                    'role': 'writer',
                    'emailAddress': email
                }
                service.permissions().create(
                    fileId=doc_id, 
                    body=user_permission, 
                    sendNotificationEmails=False,
                    supportsAllDrives=True
                ).execute()
            except Exception as share_err:
                # Ignore duplicate sharing errors or domain restriction warnings
                pass
                
        # Make document publicly readable via link (Anyone can view)
        try:
            public_permission = {
                'type': 'anyone',
                'role': 'reader'
            }
            service.permissions().create(
                fileId=doc_id,
                body=public_permission,
                supportsAllDrives=True
            ).execute()
            logger.info(f"Configured public sharing permission for Google Doc: {doc_id}")
        except Exception as public_err:
            logger.error(f"Failed to set public sharing permission for Google Doc {doc_id}: {public_err}")
                
        return web_link
        
    except Exception as e:
        logger.error(f"Failed to upload report to Google Docs: {e}", exc_info=True)
        return None
