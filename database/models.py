from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from database.connection import Base

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ticket_id = Column(String(30), unique=True, index=True, nullable=False)
    
    # Enterprise SAP Fields
    system_id = Column(String(10), default="PRD", index=True)
    client = Column(String(10), default="100")
    component = Column(String(50), default="GENERAL", index=True)
    tcode = Column(String(20), nullable=True)
    category = Column(String(50), default="Incident", index=True)
    priority = Column(String(20), default="3-Medium", index=True)
    
    # Customer Details
    customer_name = Column(String(100), nullable=False)
    customer_email = Column(String(100), nullable=False)
    company_name = Column(String(100), nullable=True)
    
    # Issue Details
    subject = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    attachment_path = Column(Text, nullable=True)
    
    # Status & Timestamps
    status = Column(String(30), default="NEW", index=True)
    created_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_time = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Database Indexes for Fast Enterprise Search
    __table_args__ = (
        Index("idx_ticket_search", "status", "priority", "system_id", "component"),
    )

    def __repr__(self):
        return f"<Ticket {self.ticket_id} - {self.customer_name} ({self.status})>"
