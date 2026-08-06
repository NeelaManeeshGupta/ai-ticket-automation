import os
import logging
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)

# Scopes required for Gmail API read access
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']

class GmailClient:
    """Gmail OAuth Client wrapper with graceful fallback for mock mode."""

    def __init__(self):
        self.service = None
        self.is_mock = settings.USE_MOCK_GMAIL

    def get_service(self):
        """Initializes and returns the Gmail API service instance, or None if in mock mode."""
        if self.is_mock:
            logger.info("Gmail Client operating in MOCK mode (USE_MOCK_GMAIL=True).")
            return None

        credentials_path = settings.GMAIL_CREDENTIALS_FILE
        token_path = settings.GMAIL_TOKEN_FILE

        if not os.path.exists(credentials_path) and not os.path.exists(token_path):
            logger.warning(
                f"Gmail credentials not found at '{credentials_path}'. Falling back to MOCK mode."
            )
            self.is_mock = True
            return None

        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            creds = None
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(credentials_path):
                        logger.error(f"Cannot initialize Gmail API: Missing {credentials_path}")
                        self.is_mock = True
                        return None
                    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)

                with open(token_path, 'w') as token_file:
                    token_file.write(creds.to_json())

            self.service = build('gmail', 'v1', credentials=creds)
            logger.info("Gmail API service connected successfully.")
            return self.service

        except Exception as e:
            logger.error(f"Failed to initialize Gmail API service: {str(e)}. Falling back to mock mode.")
            self.is_mock = True
            return None

    def watch_inbox(self, topic_name: Optional[str] = None) -> dict:
        """Registers a Gmail Watch subscription to forward incoming email events to Google Cloud Pub/Sub."""
        service = self.get_service()
        if self.is_mock or service is None:
            logger.info("Mock GmailClient: Watch setup simulated.")
            return {"historyId": "MOCK_HIST_9999", "expiration": "1799999999000"}

        topic = topic_name or settings.GMAIL_PUBSUB_TOPIC
        if not topic:
            raise ValueError("GMAIL_PUBSUB_TOPIC environment variable is not configured.")

        request_body = {
            'topicName': topic,
            'labelIds': ['INBOX'],
            'labelFilterBehavior': 'INCLUDE'
        }
        res = service.users().watch(userId='me', body=request_body).execute()
        logger.info(f"Gmail watch setup successful for topic '{topic}'. Response: {res}")
        return res

    def stop_watch(self) -> bool:
        """Stops active Gmail Push Notification watch subscription."""
        service = self.get_service()
        if self.is_mock or service is None:
            return True
        service.users().stop(userId='me').execute()
        logger.info("Gmail watch stopped successfully.")
        return True

gmail_client = GmailClient()

