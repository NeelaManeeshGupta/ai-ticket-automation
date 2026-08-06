import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from api.deps import get_db
from services.ticket_service import ticket_service
from services.email_processor import email_processor
from schemas.ticket_schemas import TicketResponse, TicketFilter
from schemas.email_schemas import ProcessEmailResponse, EmailPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["SAP Tickets & Automation"])

@router.get("", response_model=List[TicketResponse], summary="List all SAP support tickets")
def get_all_tickets(
    status: Optional[str] = Query(None, description="Filter by status (NEW, IN_PROGRESS, RESOLVED)"),
    priority: Optional[str] = Query(None, description="Filter by priority (1-Very High, 2-High, 3-Medium, 4-Low)"),
    system_id: Optional[str] = Query(None, description="Filter by SAP System ID (PRD, DEV, QAS)"),
    component: Optional[str] = Query(None, description="Filter by SAP Component (SD-BF, MM-PUR, FI-CO, BASIS)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """
    Retrieve all created support tickets.
    Supports filtering by status, priority, system_id, and component.
    """
    filters = TicketFilter(
        status=status,
        priority=priority,
        system_id=system_id,
        component=component,
        skip=skip,
        limit=limit
    )
    tickets = ticket_service.get_tickets(db, filters)
    return tickets

@router.get("/{identifier}", response_model=TicketResponse, summary="Get ticket by ID or Ticket Number")
def get_ticket_details(identifier: str, db: Session = Depends(get_db)):
    """
    Fetch ticket details by ticket_id string (e.g. 'SAP-INC-1001') or database integer ID (e.g. 1).
    """
    ticket = ticket_service.get_ticket_by_id(db, identifier)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket with ID or Ticket Number '{identifier}' not found."
        )
    return ticket

@router.post("/process-email", response_model=ProcessEmailResponse, summary="Trigger Gmail reading & ticket creation")
def trigger_email_processing(db: Session = Depends(get_db)):
    """
    Manually trigger checking unread customer emails and converting them into SAP support tickets.
    """
    logger.info("Manual trigger received for /tickets/process-email")
    response = email_processor.process_unread_inbox(db)
    return response

@router.post("/process-mock-email", response_model=ProcessEmailResponse, summary="Test email processing with custom payload")
def process_mock_email_payload(payload: EmailPayload, db: Session = Depends(get_db)):
    """
    Post a custom email payload to test OCR, AI extraction, and ticket creation locally.
    """
    logger.info(f"Custom mock email payload received from {payload.sender_email}")
    ticket_id = email_processor.process_single_email(db, payload)
    return ProcessEmailResponse(
        success=True,
        processed_count=1,
        tickets_created=[ticket_id],
        message=f"Successfully processed email and created ticket {ticket_id}."
    )

@router.patch("/{identifier}/status", response_model=TicketResponse, summary="Update ticket status")
def update_ticket_status(identifier: str, status_val: str = Query(..., alias="status"), db: Session = Depends(get_db)):
    """
    Update ticket status (NEW, IN_PROGRESS, RESOLVED, CLOSED).
    """
    ticket = ticket_service.update_ticket_status(db, identifier, status_val)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket with ID '{identifier}' not found."
        )
    return ticket

@router.post("/purge-non-sap", summary="Purge non-SAP marketing and newsletter tickets from database")
def purge_non_sap_tickets(db: Session = Depends(get_db)):
    """
    Cleans up any non-SAP promotional/marketing tickets from SQLite.
    """
    from database.models import Ticket
    import re

    all_tickets = db.query(Ticket).all()
    deleted_count = 0
    non_sap_senders = ["redditmail.com", "daily.dev", "newsletter", "no-reply", "noreply@google.com"]
    
    for t in all_tickets:
        text = f"{t.subject or ''} {t.description or ''} {t.customer_email or ''}".lower()
        sap_patterns = [r"\bsap\b", r"\btcode\b", r"\bva01\b", r"\bme21n\b", r"\bfb01\b", r"\bst22\b", r"\bsu53\b", r"\bprd\b", r"\bdev\b", r"\bqas\b"]
        has_sap = any(re.search(pat, text) for pat in sap_patterns)
        is_marketing = any(ns in text for ns in non_sap_senders) or "digest" in text or "non-incident" in text
        
        if is_marketing and not has_sap:
            db.delete(t)
            deleted_count += 1
            
@router.delete("/clear-all", summary="Delete all tickets from database for a fresh start")
def clear_all_tickets(db: Session = Depends(get_db)):
    """
    Clears all existing tickets from the database.
    """
    from database.models import Ticket
    deleted_count = db.query(Ticket).delete()
    db.commit()
    logger.info(f"Cleared {deleted_count} tickets from database.")
    return {"status": "success", "cleared_count": deleted_count}
