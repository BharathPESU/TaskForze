import os
import json
from datetime import datetime
from typing import Optional, Dict, Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from nexus.tools.google_auth import get_google_credentials
from nexus.db.models import Task, Note

logger = structlog.get_logger(__name__)

def get_drive_service():
    """Gets the Google Drive API service client."""
    creds = get_google_credentials()
    if not creds:
        return None
    return build('drive', 'v3', credentials=creds)

def get_or_create_taskforze_folder() -> Optional[str]:
    """Finds or creates the 'taskforze' folder in Google Drive."""
    service = get_drive_service()
    if not service:
        logger.warning("No google credentials found, cannot sync to Drive.")
        return None
        
    folder_name = "taskforze"
    mime_type = 'application/vnd.google-apps.folder'
    
    try:
        # Search for folder (created by the app so we have access to it)
        query = f"name='{folder_name}' and mimeType='{mime_type}' and trashed=false"
        response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = response.get('files', [])
        
        if files:
            folder_id = files[0]['id']
            logger.info("Found existing taskforze Drive folder", folder_id=folder_id)
            return folder_id
            
        # Create if not found
        file_metadata = {
            'name': folder_name,
            'mimeType': mime_type
        }
        
        folder = service.files().create(body=file_metadata, fields='id').execute()
        folder_id = folder.get('id')
        logger.info("Created new taskforze Drive folder", folder_id=folder_id)
        return folder_id
    except Exception as e:
        logger.error("Failed to get or create Google Drive folder", exc_info=e)
        return None

def upload_file_to_drive(file_path: str, mime_type: str, file_name: str, folder_id: str) -> bool:
    """Uploads a local file to the specified Google Drive folder."""
    service = get_drive_service()
    if not service:
        return False
        
    try:
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        logger.info("Uploaded file to drive", file_id=file.get('id'), file_name=file_name)
        return True
    except Exception as e:
        logger.error("Failed to upload file to drive", file_path=file_path, exc_info=e)
        return False

async def export_data_to_json(session: AsyncSession, filepath: str):
    """Exports SQLite records to a JSON file."""
    try:
        tasks_res = await session.execute(select(Task))
        tasks = tasks_res.scalars().all()
        notes_res = await session.execute(select(Note))
        notes = notes_res.scalars().all()
        
        data = {
            "tasks": [
                {
                    "title": t.title,
                    "description": t.description,
                    "status": t.status,
                    "priority": t.priority,
                    "created_at": t.created_at.isoformat() if t.created_at else None
                } for t in tasks
            ],
            "notes": [
                {
                    "title": n.title,
                    "content": n.content,
                    "created_at": n.created_at.isoformat() if n.created_at else None
                } for n in notes
            ]
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        return True
    except Exception as e:
        logger.error("Failed to export JSON data", exc_info=e)
        return False

async def sync_data_to_drive(session: AsyncSession) -> Dict[str, Any]:
    """Orchestrates backing up the SQLite DB and JSON representation to Google Drive."""
    folder_id = get_or_create_taskforze_folder()
    if not folder_id:
        return {"status": "error", "message": "Failed to get/create Google Drive folder or not authenticated. Re-authenticate in setup_auth.py to grant Drive scopes."}
        
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # 1. Upload JSON extract
    json_path = os.path.join(os.getcwd(), f"taskforze_data_{ts}.json")
    json_exported = await export_data_to_json(session, json_path)
    
    if json_exported and os.path.exists(json_path):
        upload_file_to_drive(json_path, 'application/json', f"taskforze_data_{ts}.json", folder_id)
        os.remove(json_path) # cleanup
        
    # 2. Upload SQLite Database Copy
    db_path = os.path.join(os.getcwd(), "nexus_dev.db")
    if os.path.exists(db_path):
        upload_file_to_drive(db_path, 'application/x-sqlite3', f"nexus_dev_backup_{ts}.db", folder_id)
        
    return {"status": "success", "message": f"Successfully backed up data to Drive folder ID {folder_id}."}
