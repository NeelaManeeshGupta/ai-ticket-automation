import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from config import settings
from database.connection import init_db, get_db
from api.ticket_routes import router as ticket_router
from api.webhook_routes import router as webhook_router
from gmail.gmail_client import gmail_client
from services.email_processor import email_processor
from schemas.email_schemas import ProcessEmailResponse

# Configure Logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

def _poll_sync():
    from database.connection import SessionLocal
    with SessionLocal() as db:
        res = email_processor.process_unread_inbox(db)
        if res.processed_count > 0:
            logger.info(f"[Background Job] Automatically created {res.processed_count} SAP ticket(s).")

async def background_email_poller():
    """Background worker task that periodically polls Gmail inbox for new unread emails in a worker thread."""
    logger.info(f"Background email polling initialized (Interval: {settings.EMAIL_POLL_INTERVAL_SECONDS}s).")
    import asyncio
    while True:
        try:
            await asyncio.sleep(settings.EMAIL_POLL_INTERVAL_SECONDS)
            if settings.ENABLE_BACKGROUND_POLLING:
                await asyncio.to_thread(_poll_sync)
        except asyncio.CancelledError:
            logger.info("Background email poller task cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in background email polling loop: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown actions."""
    logger.info(f"Starting {settings.PROJECT_NAME} in {settings.ENVIRONMENT} mode...")
    init_db()
    
    polling_task = None
    if settings.ENABLE_BACKGROUND_POLLING:
        import asyncio
        polling_task = asyncio.create_task(background_email_poller())

    # Auto-renew Gmail Watch subscription if configured
    if settings.GMAIL_PUBSUB_TOPIC:
        try:
            logger.info(f"Initializing Gmail Watch subscription for topic '{settings.GMAIL_PUBSUB_TOPIC}'...")
            gmail_client.watch_inbox()
        except Exception as e:
            logger.warning(f"Could not auto-start Gmail Watch subscription: {e}")
        
    yield
    
    if polling_task:
        polling_task.cancel()
    logger.info("Shutting down AI Ticket Automation Backend...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Enterprise AI Automation Backend Service for SAP Support Ticket Portal",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(ticket_router)
app.include_router(webhook_router)

# Direct endpoint aliases for requested top-level routes
@app.post("/process-email", response_model=ProcessEmailResponse, tags=["Top-Level Process Endpoint"])
def process_email_toplevel(db: Session = Depends(get_db)):
    """
    Top-level endpoint alias for POST /process-email as specified in backend API requirements.
    """
    return email_processor.process_unread_inbox(db)

from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Static Directory Setup
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", tags=["System Root"])
def root_redirect():
    """Redirect root path to interactive dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard", tags=["System Root"])
def get_dashboard():
    """Serves the live interactive SAP Support AI Ticket Portal Web Dashboard."""
    dashboard_file = STATIC_DIR / "index.html"
    if dashboard_file.exists():
        return FileResponse(str(dashboard_file))
    return {"message": "Dashboard file not found."}

@app.get("/health", tags=["System Root"])
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_excludes=["sap_tickets.db*", "uploads/*", "gmail/token.json"])
