import os
import base64
import logging
from pathlib import Path
from typing import List, Dict, Any
from config import settings
from gmail.gmail_client import gmail_client
from schemas.email_schemas import EmailPayload, EmailAttachment

logger = logging.getLogger(__name__)

class EmailReader:
    """Reads customer emails from Gmail inbox or generates mock support emails."""

    def __init__(self):
        self.upload_dir = settings.absolute_upload_dir

    def fetch_unread_emails(self) -> List[EmailPayload]:
        """Fetch unread customer support emails."""
        return self.fetch_emails()

    def fetch_emails(self) -> List[EmailPayload]:
        """Fetches unread emails from Gmail API or generates mock test email payloads."""
        service = gmail_client.get_service()

        if gmail_client.is_mock or service is None:
            logger.info("Fetching emails via Mock Email Reader...")
            return self._generate_mock_emails()

        emails: List[EmailPayload] = []
        try:
            # Query unread OR recent emails from the past day so opened test emails are also captured
            results = service.users().messages().list(userId='me', q='is:unread in:anywhere OR newer_than:1d').execute()
            messages = results.get('messages', [])

            logger.info(f"Found {len(messages)} recent/unread email(s) in Gmail.")

            for msg_summary in messages:
                msg_id = msg_summary['id']
                msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
                email_payload = self._parse_gmail_message(msg_id, msg, service)
                if email_payload:
                    emails.append(email_payload)

            return emails
        except Exception as e:
            logger.error(f"Error fetching emails from Gmail API: {str(e)}. Returning mock fallback.")
            return self._generate_mock_emails()

    def mark_email_as_read(self, message_id: str):
        """Marks message as read in Gmail API if live service is active."""
        if gmail_client.is_mock or message_id.startswith("MSG-MOCK"):
            logger.info(f"Mock email {message_id} marked as read.")
            return

        service = gmail_client.get_service()
        if service:
            try:
                service.users().messages().batchModify(
                    userId='me',
                    body={'ids': [message_id], 'removeLabelIds': ['UNREAD', 'SPAM']}
                ).execute()
                logger.info(f"Email {message_id} marked as read in Gmail.")
            except Exception as e:
                logger.error(f"Failed to mark email {message_id} as read: {str(e)}")

    def _parse_gmail_message(self, msg_id: str, msg: Dict[str, Any], service) -> EmailPayload:
        """Parses raw Gmail API message structure into EmailPayload."""
        payload = msg.get('payload', {})
        headers = payload.get('headers', [])

        sender_email = "unknown@customer.com"
        sender_name = "Unknown Customer"
        subject = "No Subject"

        for h in headers:
            name = h.get('name', '').lower()
            val = h.get('value', '')
            if name == 'from':
                if '<' in val:
                    sender_name = val.split('<')[0].strip(' "\'')
                    sender_email = val.split('<')[1].strip('>')
                else:
                    sender_email = val
                    sender_name = val.split('@')[0]
            elif name == 'subject':
                subject = val

        # Extract body text
        body = self._extract_body(payload)
        
        # Download attachments
        attachments = self._download_attachments(msg_id, payload, service)

        return EmailPayload(
            message_id=msg_id,
            sender_name=sender_name,
            sender_email=sender_email,
            subject=subject,
            body=body,
            attachments=attachments
        )

    def _extract_body(self, payload: Dict[str, Any]) -> str:
        """Extracts text content from message body parts."""
        if 'parts' in payload:
            for part in payload['parts']:
                if part.get('mimeType') == 'text/plain':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        elif 'body' in payload:
            data = payload.get('body', {}).get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        return ""

    def _download_attachments(self, msg_id: str, payload: Dict[str, Any], service) -> List[EmailAttachment]:
        """Downloads attachment files and saves them to local storage."""
        attachments: List[EmailAttachment] = []
        parts = payload.get('parts', [])

        for part in parts:
            filename = part.get('filename')
            body = part.get('body', {})
            attachment_id = body.get('attachmentId')

            if filename and attachment_id:
                try:
                    att_data = service.users().messages().attachments().get(
                        userId='me', messageId=msg_id, id=attachment_id
                    ).execute()
                    file_bytes = base64.urlsafe_b64decode(att_data.get('data', ''))
                    
                    save_path = self.upload_dir / f"{msg_id}_{filename}"
                    with open(save_path, 'wb') as f:
                        f.write(file_bytes)

                    attachments.append(EmailAttachment(
                        filename=filename,
                        content_type=part.get('mimeType', 'application/octet-stream'),
                        file_path=str(save_path),
                        file_size=len(file_bytes)
                    ))
                except Exception as e:
                    logger.error(f"Failed to download attachment {filename}: {str(e)}")

        return attachments

    def _generate_mock_emails(self) -> List[EmailPayload]:
        """Generates realistic SAP customer issue mock emails for local testing."""
        mock_attachment_path = self.upload_dir / "mock_sap_error.png"
        
        # Create a sample image if it doesn't exist
        if not mock_attachment_path.exists():
            try:
                from PIL import Image, ImageDraw
                img = Image.new('RGB', (600, 200), color=(240, 240, 240))
                d = ImageDraw.Draw(img)
                d.text((20, 30), "SAP ERP System - Error Notification", fill=(0, 0, 0))
                d.text((20, 80), "SAP Error Message: Document type OR is not allowed", fill=(200, 0, 0))
                d.text((20, 120), "Transaction Code: VA01 | User: JDOE", fill=(50, 50, 50))
                img.save(mock_attachment_path)
            except Exception as e:
                logger.warning(f"Could not generate sample PIL image: {e}")
                with open(mock_attachment_path, 'w') as f:
                    f.write("SAP Error Message: Document type OR is not allowed")

        return [
            EmailPayload(
                message_id="MSG-MOCK-001",
                sender_name="Sarah Jenkins",
                sender_email="sarah.jenkins@globallogistics.com",
                company_name="Global Logistics Inc",
                subject="URGENT: SAP Order Creation Failure in PRD System - Document type OR not allowed",
                body=(
                    "Dear SAP Support Team,\n\n"
                    "We are facing a critical blocker in our PRD system (Client 100). "
                    "When attempting to create a Standard Sales Order using transaction code VA01, "
                    "the system blocks submission with the following error code and message:\n\n"
                    "SAP Error Message: Document type OR is not allowed\n\n"
                    "System: PRD\nClient: 100\nModule: SD-BF\n"
                    "Please refer to the attached screenshot for full system details.\n\n"
                    "Thanks,\nSarah Jenkins\nGlobal Logistics Inc"
                ),
                attachments=[
                    EmailAttachment(
                        filename="mock_sap_error.png",
                        content_type="image/png",
                        file_path=str(mock_attachment_path),
                        file_size=os.path.getsize(mock_attachment_path) if mock_attachment_path.exists() else 1024
                    )
                ]
            )
        ]

email_reader = EmailReader()
