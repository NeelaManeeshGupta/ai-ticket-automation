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
    x_goog_channel_token: Optional[str] = Header(None, alias="X-Goog-Channel-Token")
):
    """
    Receives push notifications from Google Cloud Pub/Sub when a new email arrives in Gmail.
    Acknowledges receipt immediately (<100ms) and delegates processing to a background task.
    """
    logger.info("Received push notification from Gmail Pub/Sub Webhook.")

    if settings.WEBHOOK_SECRET_TOKEN and x_goog_channel_token:
        if x_goog_channel_token != settings.WEBHOOK_SECRET_TOKEN:
            logger.warning("Unauthorized webhook request: Invalid security token.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Webhook Channel Token"
            )

    msg_data = payload.get("message", {})
    raw_data = msg_data.get("data")
    message_id = msg_data.get("messageId", "UNKNOWN")

    decoded_json = {}
    if raw_data:
        try:
            decoded_bytes = base64.b64decode(raw_data)
            decoded_json = json.loads(decoded_bytes.decode('utf-8'))
            logger.info(f"Decoded Webhook Payload: {decoded_json}")
        except Exception as err:
            logger.warning(f"Could not decode base64 webhook data: {err}")

    background_tasks.add_task(process_gmail_webhook_background)

    return {
        "status": "accepted",
        "message_id": message_id,
        "history_id": decoded_json.get("historyId"),
        "email_address": decoded_json.get("emailAddress")
    }

@router.post("/gmail/watch", summary="Renew Gmail Watch Subscription")
def renew_gmail_watch():
    """
    Registers or renews the Gmail Push Notification watch subscription with GCP Pub/Sub.
    """
    res = gmail_client.watch_inbox()
    if not res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=res.get("message")
        )
    return res

@router.post("/gmail/stop-watch", summary="Stop Gmail Watch Subscription")
def stop_gmail_watch():
    """
    Stops the active Gmail Push Notification watch subscription.
    """
    return gmail_client.stop_watch()
