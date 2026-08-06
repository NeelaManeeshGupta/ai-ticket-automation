import base64
import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Header, status
from sqlalchemy.orm import Session
from database.connection import SessionLocal, get_db
from gmail.gmail_client import gmail_client
from services.email_processor import email_processor
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["Gmail Webhooks"])

def process_gmail_webhook_background():
    """Background execution task to fetch and process incoming emails without blocking webhook response."""
    db: Session = SessionLocal()
    try:
        logger.info("Executing background email processing for Webhook notification...")
        res = email_processor.process_unread_inbox(db)
        logger.info(f"Webhook background execution complete: {res.message}")
    except Exception as e:
        logger.error(f"Error executing webhook background email processing: {str(e)}")
    finally:
        db.close()

@router.post("/gmail", status_code=status.HTTP_200_OK)
def receive_gmail_webhook(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    x_webhook_token: Optional[str] = Header(None)
):
    """
    Production Webhook Endpoint for Google Cloud Pub/Sub Push Notifications.
    Decodes the incoming notification and triggers email extraction in a background task.
    """
    logger.info("Received raw Gmail Webhook event from Google Cloud Pub/Sub.")

    message = payload.get("message", {})
    if not message:
        logger.warning("Received invalid Pub/Sub payload structure.")
        return {"status": "ignored", "reason": "No message field found"}

    data_b64 = message.get("data")
    decoded_event = {}
    if data_b64:
        try:
            decoded_bytes = base64.b64decode(data_b64)
            decoded_event = json.loads(decoded_bytes.decode("utf-8"))
            logger.info(f"Decoded Gmail Pub/Sub Event: {decoded_event}")
        except Exception as e:
            logger.error(f"Failed to decode Pub/Sub base64 data: {e}")

    # Add processing to FastAPI background task queue to return HTTP 200 to Pub/Sub instantly
    background_tasks.add_task(process_gmail_webhook_background)

    return {
        "status": "accepted",
        "message_id": message.get("messageId"),
        "history_id": decoded_event.get("historyId"),
        "email_address": decoded_event.get("emailAddress")
    }

@router.post("/gmail/watch", status_code=status.HTTP_200_OK)
def trigger_gmail_watch(topic_name: Optional[str] = None):
    """
    Triggers/Renews the Gmail API Watch subscription with Google Cloud Pub/Sub.
    Must be called every 7 days (or on server startup) in production.
    """
    try:
        watch_response = gmail_client.watch_inbox(topic_name=topic_name)
        return {
            "status": "success",
            "message": "Gmail Watch subscription successfully created/renewed.",
            "details": watch_response
        }
    except Exception as e:
        logger.error(f"Failed to create Gmail watch subscription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to setup Gmail Watch: {str(e)}"
        )

@router.post("/gmail/stop-watch", status_code=status.HTTP_200_OK)
def stop_gmail_watch():
    """Stops the active Gmail Watch subscription."""
    success = gmail_client.stop_watch()
    return {"status": "success" if success else "failed", "message": "Gmail Watch stopped."}
