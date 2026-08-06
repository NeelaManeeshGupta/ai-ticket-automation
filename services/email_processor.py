import json
import logging
from typing import List
from sqlalchemy.orm import Session
from gmail.email_reader import email_reader
from services.ocr_service import ocr_service
from services.llm_extractor import llm_extractor
from services.ticket_service import ticket_service
from schemas.ticket_schemas import TicketCreate
from schemas.email_schemas import EmailPayload, ProcessEmailResponse

logger = logging.getLogger(__name__)

class EmailProcessorService:
    """Orchestrates incoming customer emails into SAP Support Tickets."""

    def process_unread_inbox(self, db: Session) -> ProcessEmailResponse:
        """Fetches unread emails from Gmail and processes each into a ticket."""
        logger.info("Starting unread email processing pipeline...")
        emails = email_reader.fetch_emails()

        if not emails:
            return ProcessEmailResponse(
                success=True,
                processed_count=0,
                tickets_created=[],
                message="No unread customer support emails found."
            )

        tickets_created = []
        for email in emails:
            try:
                ticket_id = self.process_single_email(db, email)
                if ticket_id:
                    tickets_created.append(ticket_id)
                email_reader.mark_email_as_read(email.message_id)
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to process email {email.message_id} from {email.sender_email}: {str(e)}")

        return ProcessEmailResponse(
            success=True,
            processed_count=len(emails),
            tickets_created=tickets_created,
            message=f"Successfully processed {len(tickets_created)} email(s) into SAP support tickets."
        )

    def process_single_email(self, db: Session, email: EmailPayload) -> str:
        """Processes a single email payload end-to-end and saves a Ticket."""
        logger.info(f"Processing email from {email.sender_email} (Subject: {email.subject})")

        # Step 1: Run OCR on attachments & prepare image bytes
        ocr_text = ""
        attachment_paths = []
        image_parts = []
        if email.attachments:
            ocr_text = ocr_service.extract_text_from_attachments(email.attachments)
            attachment_paths = [att.file_path for att in email.attachments]
            image_parts = ocr_service.get_image_attachment_parts(email.attachments)

        # Step 2: Extract structured incident data via AI / LLM Layer
        extraction = llm_extractor.extract_incident_data(
            sender_name=email.sender_name,
            sender_email=email.sender_email,
            subject=email.subject,
            email_body=email.body,
            ocr_text=ocr_text,
            image_parts=image_parts
        )

        # Step 2.5: Guard against Non-SAP / Marketing / Personal emails
        if extraction.is_sap_incident is False:
            logger.info(f"Filtered out non-SAP email '{email.subject}' from {email.sender_email}. Reason: {extraction.relevance_reason}")
            return None

        # Step 3: Create Enterprise SAP Ticket payload
        ticket_create = TicketCreate(
            system_id=extraction.system_id or "PRD",
            client=extraction.client or "100",
            component=extraction.component or "GENERAL",
            tcode=extraction.tcode or None,
            category=extraction.category or "Incident",
            priority=extraction.priority or "3-Medium",
            customer_name=extraction.customer_name or email.sender_name,
            customer_email=extraction.customer_email or email.sender_email,
            company_name=extraction.company_name or email.company_name,
            subject=email.subject,
            description=extraction.problem_description or email.body,
            error_code=extraction.error_code or None,
            error_message=extraction.error_message or None,
            attachment_path=json.dumps(attachment_paths) if attachment_paths else None,
            status="NEW"
        )

        # Step 4: Persist in Database
        ticket = ticket_service.create_ticket(db, ticket_create)
        return ticket.ticket_id

email_processor = EmailProcessorService()
