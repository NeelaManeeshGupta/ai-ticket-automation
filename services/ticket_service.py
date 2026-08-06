import logging
import re
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database.models import Ticket
from schemas.ticket_schemas import TicketCreate, TicketFilter

logger = logging.getLogger(__name__)

class TicketService:
    """Service layer managing SAP Support Ticket creation and retrieval."""

    def generate_next_ticket_id(self, db: Session) -> str:
        """Generates sequential ticket ID like SAP-INC-1001, SAP-INC-1002."""
        last_ticket = db.query(Ticket).order_by(desc(Ticket.id)).first()
        
        if not last_ticket or not last_ticket.ticket_id:
            return "SAP-INC-1001"

        # Extract numerical suffix
        match = re.search(r"(\d+)$", last_ticket.ticket_id)
        if match:
            next_num = int(match.group(1)) + 1
            return f"SAP-INC-{next_num}"
        
        return f"SAP-INC-{last_ticket.id + 1001}"

    def create_ticket(self, db: Session, ticket_in: TicketCreate) -> Ticket:
        """Creates a new support ticket in the database."""
        if not ticket_in.ticket_id:
            ticket_in.ticket_id = self.generate_next_ticket_id(db)

        logger.info(f"Creating ticket {ticket_in.ticket_id} for {ticket_in.customer_email}")

        db_ticket = Ticket(
            ticket_id=ticket_in.ticket_id,
            system_id=ticket_in.system_id,
            client=ticket_in.client,
            component=ticket_in.component,
            tcode=ticket_in.tcode,
            category=ticket_in.category,
            priority=ticket_in.priority,
            customer_name=ticket_in.customer_name,
            customer_email=ticket_in.customer_email,
            company_name=ticket_in.company_name,
            subject=ticket_in.subject,
            description=ticket_in.description,
            error_code=ticket_in.error_code,
            error_message=ticket_in.error_message,
            attachment_path=ticket_in.attachment_path,
            status=ticket_in.status or "NEW"
        )

        db.add(db_ticket)
        db.commit()
        db.refresh(db_ticket)
        logger.info(f"Ticket {db_ticket.ticket_id} saved successfully with ID {db_ticket.id}.")
        return db_ticket

    def get_tickets(self, db: Session, filters: TicketFilter) -> List[Ticket]:
        """Retrieves tickets with optional filters and pagination."""
        query = db.query(Ticket)

        if filters.status:
            query = query.filter(Ticket.status == filters.status)
        if filters.priority:
            query = query.filter(Ticket.priority == filters.priority)
        if filters.system_id:
            query = query.filter(Ticket.system_id == filters.system_id)
        if filters.component:
            query = query.filter(Ticket.component == filters.component)

        return query.order_by(desc(Ticket.created_time)).offset(filters.skip).limit(filters.limit).all()

    def get_ticket_by_id(self, db: Session, identifier: str) -> Optional[Ticket]:
        """Lookup ticket by ticket_id string (e.g. SAP-INC-1001) or primary key int."""
        if identifier.isdigit():
            ticket = db.query(Ticket).filter(Ticket.id == int(identifier)).first()
            if ticket:
                return ticket

        return db.query(Ticket).filter(Ticket.ticket_id == identifier.upper()).first()

ticket_service = TicketService()
