from typing import List, Optional
from pydantic import BaseModel, Field

class EmailAttachment(BaseModel):
    filename: str
    content_type: str
    file_path: str
    file_size: int

class EmailPayload(BaseModel):
    message_id: str = Field(default="MSG-LOCAL-001")
    sender_name: str = Field(default="John Doe")
    sender_email: str = Field(default="john.doe@acme-corp.com")
    company_name: Optional[str] = Field(default="Acme Corp")
    subject: str = Field(default="SAP Error: Document type OR is not allowed in sales order creation")
    body: str = Field(default="Hi Support Team,\n\nWe are facing an issue when trying to create a sales order in PRD system 100 via transaction VA01. It throws error: 'Document type OR is not allowed'. Please check attached screenshot.\n\nRegards,\nJohn Doe\nAcme Corp")
    attachments: List[EmailAttachment] = Field(default_factory=list)

class ProcessEmailResponse(BaseModel):
    success: bool
    processed_count: int
    tickets_created: List[str]
    message: str
