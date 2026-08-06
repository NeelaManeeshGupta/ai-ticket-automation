import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

logger = logging.getLogger(__name__)

db_url = settings.DATABASE_URL
if os.environ.get("VERCEL"):
    db_url = "sqlite:////tmp/sap_tickets.db"

# Configure connect_args for SQLite thread safety & lock timeout
connect_args = {}
if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(
    db_url,
    connect_args=connect_args,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

_db_initialized = False

def get_db():
    """Dependency generator for FastAPI database session injection."""
    global _db_initialized
    if not _db_initialized:
        try:
            init_db()
            _db_initialized = True
        except Exception as e:
            logger.warning(f"Lazy init_db execution: {e}")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Creates database tables if they do not already exist and seeds sample tickets if empty."""
    logger.info("Initializing Database schema...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized successfully.")

    try:
        db = SessionLocal()
        from database.models import Ticket
        if db.query(Ticket).count() == 0:
            logger.info("Seeding initial SAP support tickets for presentation...")
            demo_tickets = [
                Ticket(
                    ticket_id="SAP-INC-1001",
                    system_id="PRD",
                    client="100",
                    component="SD-BF",
                    tcode="VA01",
                    category="Configuration Error",
                    priority="1-Very High",
                    customer_name="Sarah Jenkins",
                    customer_email="sarah.jenkins@globallogistics.com",
                    company_name="Global Logistics Corp",
                    subject="URGENT: SAP Order Creation Failure in PRD System",
                    description="Order creation failing in VA01. Error: Document type OR is not allowed for Sales Org 1000.",
                    error_code="ERR_DOC_TYPE_OR",
                    error_message="Document type OR is not allowed for Sales Org 1000",
                    status="NEW"
                ),
                Ticket(
                    ticket_id="SAP-INC-1002",
                    system_id="QAS",
                    client="100",
                    component="BTP-JOULE",
                    tcode=None,
                    category="Service Outage",
                    priority="2-High",
                    customer_name="David",
                    customer_email="david@abctechnologies.com",
                    company_name="ABC Technologies Pvt Ltd",
                    subject="SAP Joule Unable to Execute User Requests",
                    description="Users facing issue with SAP Joule in QAS environment. System not returning response for pending approval tasks.",
                    error_code=None,
                    error_message="SAP Joule Unable to Execute User Requests",
                    status="IN_PROGRESS"
                ),
                Ticket(
                    ticket_id="SAP-INC-1003",
                    system_id="DEV",
                    client="100",
                    component="BASIS",
                    tcode="ST22",
                    category="Short Dump",
                    priority="2-High",
                    customer_name="Elena Rostova",
                    customer_email="elena@techcorp.de",
                    company_name="TechCorp GmbH",
                    subject="CRITICAL: ABAP Short Dump CX_SY_ZERODIVIDE in DEV 100",
                    description="Short dump occurred during custom ABAP report execution in transaction ST22.",
                    error_code="CX_SY_ZERODIVIDE",
                    error_message="Division by zero exception CX_SY_ZERODIVIDE",
                    status="NEW"
                )
            ]
            db.add_all(demo_tickets)
            db.commit()
            logger.info("Demo tickets seeded successfully.")
    except Exception as e:
        logger.warning(f"Failed to seed demo tickets: {str(e)}")
    finally:
        db.close()
