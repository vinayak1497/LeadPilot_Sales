"""
FastAPI application for the SalesShortcut UI Client.

Provides a web interface to manage sales agent workflows including lead finding,
SDR engagement, lead management, and calendar scheduling. Features real-time
updates via WebSocket and A2A integration with sales agents.
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from datetime import datetime
from enum import Enum

# Common project imports
import common.config as config
import httpx
from pydantic import BaseModel, Field, ValidationError

from fastapi import Depends, FastAPI, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

UI_CLIENT_LOGGER = "UIClient"
BUSINESS_LOGIC_LOGGER = "BusinessLogic"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(UI_CLIENT_LOGGER)

# A2A SDK Imports (optional - fallback to simple HTTP if not available)
try:
    from a2a.client import A2AClient, A2AClientHTTPError, A2AClientJSONError
    from a2a.types import DataPart as A2ADataPart
    from a2a.types import JSONRPCErrorResponse
    from a2a.types import SendMessageSuccessResponse
    from a2a.types import Message as A2AMessage
    from a2a.types import MessageSendConfiguration, MessageSendParams
    from a2a.types import Role as A2ARole
    from a2a.types import SendMessageRequest, SendMessageResponse
    from a2a.types import Task as A2ATask
    A2A_AVAILABLE = True
except ImportError:
    logger.warning("A2A dependencies not found, falling back to simple HTTP client")
    A2A_AVAILABLE = False

# Import direct Google Maps search for reliable lead finding (businesses without websites)
try:
    from .direct_search import direct_search_businesses
    DIRECT_SEARCH_AVAILABLE = True
    logger.info("Direct Google Maps search module loaded - finds businesses WITHOUT websites")
except ImportError as e:
    DIRECT_SEARCH_AVAILABLE = False
    logger.warning(f"Direct search module not available: {e}")

# Import SDR research module for business analysis
try:
    from .sdr_research import research_business, generate_proposal
    SDR_RESEARCH_AVAILABLE = True
    logger.info("SDR Research module loaded - provides AI-powered business analysis")
except ImportError as e:
    SDR_RESEARCH_AVAILABLE = False
    logger.warning(f"SDR Research module not available: {e}")

# Import email reply tracker for automatic lead confirmation
try:
    from .email_tracker import EmailReplyTracker, init_email_tracker, get_email_tracker
    EMAIL_TRACKER_AVAILABLE = True
    logger.info("Email Reply Tracker module loaded - monitors inbox for confirmations")
except ImportError as e:
    EMAIL_TRACKER_AVAILABLE = False
    logger.warning(f"Email tracker module not available: {e}")

# Import Clerk authentication module
try:
    from .auth import (
        get_current_user, require_auth, get_auth_state, optional_auth,
        AuthState, CLERK_PUBLISHABLE_KEY
    )
    AUTH_AVAILABLE = True
    logger.info("Clerk Authentication module loaded")
except ImportError as e:
    AUTH_AVAILABLE = False
    CLERK_PUBLISHABLE_KEY = os.environ.get(
        "CLERK_PUBLISHABLE_KEY",
        "pk_test_YWRlcXVhdGUtc3RpbmtidWctNzQuY2xlcmsuYWNjb3VudHMuZGV2JA"
    )
    logger.warning(f"Auth module not available, auth disabled: {e}")

# Import Firebase persistence service (replaces BigQuery)
try:
    from .firebase_service import (
        get_firebase_service, get_bigquery_service,
        persist_sdr_engaged, persist_lead_converting,
        persist_meeting_scheduled, persist_lead_confirmed,
        add_note_to_lead, get_lead_full_details,
        update_lead_status_by_column, LeadStatus
    )
    BIGQUERY_AVAILABLE = True  # kept as BIGQUERY_AVAILABLE for compat
    FIREBASE_AVAILABLE = True
    logger.info("Firebase persistence service loaded")
except ImportError as e:
    BIGQUERY_AVAILABLE = False
    FIREBASE_AVAILABLE = False
    logger.warning(f"Firebase service not available: {e}")

# Import calendar utilities for meeting scheduling
try:
    from lead_manager.lead_manager.tools.calendar_utils import create_meeting_with_lead
    CALENDAR_UTILS_AVAILABLE = True
    logger.info("Calendar utilities loaded for meeting scheduling")
except ImportError as e:
    CALENDAR_UTILS_AVAILABLE = False
    logger.warning(f"Calendar utilities not available: {e}")

# Ensure imports work
try:
    import common.config
except ImportError as e:
    logger.error(f"Failed to import necessary application modules: {e}")
    logger.error("Ensure you run uvicorn from the project root directory.")
    logger.error("Example: uvicorn ui_client.main:app --reload --port 8000")
    sys.exit(1)

module_dir = Path(__file__).parent
templates_dir = module_dir / "templates"
static_dir = module_dir / "static"

# Ensure static directory exists (for Cloud Run)
if not static_dir.exists():
    logger.warning(f"Static directory not found at {static_dir}, searching alternative paths...")
    # Try alternative paths for Cloud Run deployment
    alternative_paths = [
        Path("/app/sales_shortcut/ui_client/static"),
        Path("/app/ui_client/static"),
        module_dir.parent / "ui_client" / "static"
    ]
    for alt_path in alternative_paths:
        if alt_path.exists():
            static_dir = alt_path
            logger.info(f"Found static directory at {static_dir}")
            break
    else:
        logger.error(f"Static directory not found in any expected location. Checked: {[str(p) for p in [static_dir] + alternative_paths]}")

logger.info(f"Using static directory: {static_dir}")
logger.info(f"Using templates directory: {templates_dir}")

# Business Status Enums
class BusinessStatus(str, Enum):
    FOUND = "found"
    CONTACTED = "contacted"
    ENGAGED = "engaged"
    NOT_INTERESTED = "not_interested"
    NO_RESPONSE = "no_response"
    CONVERTING = "converting"
    MEETING_SCHEDULED = "meeting_scheduled"

class AgentType(str, Enum):
    LEAD_FINDER = "lead_finder"
    SDR = "sdr"
    LEAD_MANAGER = "lead_manager"
    CALENDAR = "calendar"

# Data Models
class Business(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    description: Optional[str] = None
    city: str
    status: BusinessStatus = BusinessStatus.FOUND
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    notes: List[str] = Field(default_factory=list)

class AgentUpdate(BaseModel):
    agent_type: AgentType
    business_id: str
    status: BusinessStatus
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)
    data: Optional[dict[str, Any]] = None

class LeadFinderRequest(BaseModel):
    city: str = Field(..., min_length=1, max_length=100, description="Target city for lead finding")

class HumanInputRequest(BaseModel):
    request_id: str
    prompt: str
    type: str
    timestamp: str

class HumanInputResponse(BaseModel):
    request_id: str
    response: str

class ScheduleMeetingRequest(BaseModel):
    """Request model for scheduling a meeting with a lead."""
    business_id: str = Field(..., description="The ID of the business to schedule a meeting with")
    title: str = Field(..., description="Meeting title")
    date: str = Field(..., description="Meeting date in YYYY-MM-DD format")
    time: str = Field(..., description="Meeting time in HH:MM format")
    duration: int = Field(default=30, description="Meeting duration in minutes")
    attendee_email: Optional[str] = Field(None, description="Optional attendee email")
    description: Optional[str] = Field(None, description="Meeting description/agenda")

# Global application state
app_state = {
    "is_running": False,
    "current_city": None,
    "businesses": {},  # dict[str, Business]
    "agent_updates": [],  # List[AgentUpdate]
    "websocket_connections": set(),  # Set[WebSocket]
    "session_id": None,
    "human_input_requests": {},  # dict[str, HumanInputRequest]
}

class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_update(self, data: dict[str, Any]):
        """Send update to all connected clients."""
        if not self.active_connections:
            return
        
        message = json.dumps(data, default=str)
        disconnected = set()
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending WebSocket message: {e}")
                disconnected.add(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

manager = ConnectionManager()

# Email tracker instance
email_tracker_instance = None

async def handle_email_confirmation(lead_info: dict):
    """Handle when an email reply confirms a lead."""
    business_id = lead_info.get("business_id")
    business_name = lead_info.get("business_name", "Unknown")
    
    logger.info(f"📧 Auto-confirming lead via email reply: {business_name}")
    
    if business_id and business_id in app_state["businesses"]:
        business = app_state["businesses"][business_id]
        business.status = "confirmed"
        business.notes.append(f"Auto-confirmed via email reply at {datetime.now().isoformat()}")
        business.notes.append(f"Confirmed by: {lead_info.get('confirmed_by', 'Unknown')}")
        
        # Send WebSocket update to move to Lead Manager
        await manager.send_update({
            "type": "lead_confirmed",
            "agent": "lead_manager",
            "business": business.model_dump(),
            "update": {
                "status": "confirmed",
                "message": f"Auto-confirmed via email reply from {lead_info.get('confirmed_by', 'recipient')}",
                "auto_confirmed": True
            },
            "timestamp": datetime.now().isoformat(),
        })
        
        # Persist to Firebase as CONVERTING (email-confirmed lead)
        if BIGQUERY_AVAILABLE:
            try:
                research_data = None
                if "sdr_results" in app_state and business_id in app_state["sdr_results"]:
                    research_data = app_state["sdr_results"][business_id].get("research")
                # Use user_info stored when the email was sent
                _auto_user = lead_info.get("user_info", {}) or {"user_id": "email_auto_confirm"}
                bq_result = await persist_lead_converting(
                    lead_id=business_id,
                    user_info=_auto_user,
                    lead_details=business.model_dump(),
                    email_details={"confirmed_by": lead_info.get("confirmed_by"), "confirmed_at": datetime.now().isoformat()},
                    research_data=research_data,
                )
                if bq_result.get("success"):
                    logger.info(f"✅ Auto-confirmed lead {business_name} persisted to Firebase (CONVERTING)")
                elif not bq_result.get("skipped"):
                    logger.error(f"❌ Firebase CONVERTING persist failed for {business_name}: {bq_result.get('error')}")
            except Exception as bq_err:
                logger.error(f"❌ Firebase persist exception for auto-confirm: {bq_err}")
        
        logger.info(f"✅ Lead {business_name} auto-confirmed and moved to Lead Manager")

async def handle_email_rejection(lead_info: dict):
    """Handle when an email reply rejects a lead."""
    business_id = lead_info.get("business_id")
    business_name = lead_info.get("business_name", "Unknown")
    
    logger.info(f"📧 Lead rejected via email reply: {business_name}")
    
    if business_id and business_id in app_state["businesses"]:
        business = app_state["businesses"][business_id]
        business.status = "rejected"
        business.notes.append(f"Rejected via email reply at {datetime.now().isoformat()}")
        
        # Send WebSocket update
        await manager.send_update({
            "type": "lead_rejected",
            "agent": "sdr",
            "business": business.model_dump(),
            "update": {
                "status": "rejected",
                "message": "Lead declined via email reply"
            },
            "timestamp": datetime.now().isoformat(),
        })


def setup_google_credentials():
    """
    Setup Google Cloud credentials for Railway deployment.
    Supports base64-encoded credentials via GOOGLE_CREDENTIALS_BASE64 env var.
    """
    import base64
    import tempfile
    
    # Check if credentials are provided as base64 (for Railway/cloud deployment)
    creds_base64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
    if creds_base64:
        try:
            # Decode base64 credentials
            creds_json = base64.b64decode(creds_base64).decode("utf-8")
            
            # Write to a temporary file
            creds_file = tempfile.NamedTemporaryFile(
                mode="w", 
                suffix=".json", 
                delete=False,
                prefix="gcp_creds_"
            )
            creds_file.write(creds_json)
            creds_file.close()
            
            # Set the environment variable
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_file.name
            logger.info(f"✅ Google credentials loaded from GOOGLE_CREDENTIALS_BASE64")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to decode GOOGLE_CREDENTIALS_BASE64: {e}")
            return False
    
    # Check for existing credentials file
    existing_creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if existing_creds and os.path.exists(existing_creds):
        logger.info(f"✅ Using existing Google credentials: {existing_creds}")
        return True
    
    # Check for local .secrets directory
    local_creds_paths = [
        ".secrets/leadpilot-gdg-ae42d1864e6a.json",
        ".secrets/gcp-credentials.json",
        "credentials.json"
    ]
    for path in local_creds_paths:
        if os.path.exists(path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
            logger.info(f"✅ Using local Google credentials: {path}")
            return True
    
    logger.warning("⚠️ No Google credentials found - Firebase persistence may still work via RTDB URL")
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup and shutdown events."""
    global email_tracker_instance
    
    logger.info("=" * 60)
    logger.info("🚀 LeadPilot UI Client starting up...")
    logger.info(f"   Environment: {'Railway' if os.environ.get('RAILWAY_ENVIRONMENT') else 'Local'}")
    logger.info(f"   Port: {os.environ.get('PORT', '8000')}")
    logger.info("=" * 60)
    
    # Setup Google Cloud credentials (Railway support)
    setup_google_credentials()
    
    # Initialize Firebase service
    if BIGQUERY_AVAILABLE:
        try:
            from .firebase_service import get_firebase_service
            fb_service = get_firebase_service()
            if fb_service.is_available():
                logger.info("✅ Firebase service initialized successfully")
            else:
                logger.warning("⚠️ Firebase service not available")
        except Exception as e:
            logger.warning(f"⚠️ Firebase initialization failed: {e}")
    
    # Initialize and start email reply tracker
    if EMAIL_TRACKER_AVAILABLE:
        try:
            email_tracker_instance = init_email_tracker(
                on_confirmation=handle_email_confirmation,
                on_rejection=handle_email_rejection
            )
            await email_tracker_instance.start()
            logger.info("📧 Email reply tracking started - monitoring inbox for confirmations")
        except Exception as e:
            logger.error(f"Failed to start email tracker: {e}")
    
    logger.info("✅ LeadPilot UI Client ready!")
    logger.info("=" * 60)
    
    yield
    
    # Cleanup
    if email_tracker_instance:
        await email_tracker_instance.stop()
    
    logger.info("👋 LeadPilot UI Client shutting down...")

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory=str(templates_dir))

# Mount static files with additional logging
logger.info(f"Mounting static files from {static_dir} to /static")
try:
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info("Static files mounted successfully")
except Exception as e:
    logger.error(f"Failed to mount static files: {e}")
    # Try to create a minimal static mount as fallback
    try:
        from fastapi.responses import FileResponse
        logger.warning("Creating fallback static file handler")
    except Exception as fallback_error:
        logger.error(f"Fallback static handler also failed: {fallback_error}")

def format_currency(value: Optional[float]) -> str:
    """Formats an optional float value as currency."""
    if value is None:
        return "N/A"
    return f"${value:,.2f}"

def format_datetime(dt: datetime) -> str:
    """Formats datetime for display."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")

# Add custom filters to templates
templates.env.filters["format_currency"] = format_currency
templates.env.filters["format_datetime"] = format_datetime

async def call_lead_finder_agent_a2a(city: str, session_id: str) -> dict[str, Any]:
    """
    Calls the Lead Finder agent via A2A to find businesses in the specified city.
    """
    business_logger = logging.getLogger(BUSINESS_LOGIC_LOGGER)
    
    lead_finder_url = os.environ.get(
        "LEAD_FINDER_SERVICE_URL", config.DEFAULT_LEAD_FINDER_URL
    ).rstrip("/")
    
    business_logger.info(f"Calling Lead Finder at {lead_finder_url} for city: {city}")
    
    outcome = {
        "success": False,
        "businesses": [],
        "error": None,
    }
    
    try:
        async with httpx.AsyncClient() as http_client:
            a2a_client = A2AClient(httpx_client=http_client, url=lead_finder_url)
            
            # Prepare A2A message
            a2a_task_id = f"lead-search-{session_id}"
            
            search_data = {
                "city": city,
            }
            
            sdk_message = A2AMessage(
                taskId=a2a_task_id,
                contextId=session_id,
                messageId=str(uuid.uuid4()),
                role=A2ARole.user,
                parts=[A2ADataPart(data=search_data)],
                metadata={"operation": "find_leads", "city": city},
            )
            
            sdk_send_params = MessageSendParams(
                message=sdk_message,
                configuration=MessageSendConfiguration(
                    acceptedOutputModes=["data", "application/json"]
                ),
            )
            
            sdk_request = SendMessageRequest(
                id=str(uuid.uuid4()), params=sdk_send_params
            )
            
            # Send request to Lead Finder
            response: SendMessageResponse = await a2a_client.send_message(sdk_request)
            root_response_part = response.root
            
            if isinstance(root_response_part, JSONRPCErrorResponse):
                actual_error = root_response_part.error
                business_logger.error(
                    f"A2A Error from Lead Finder: {actual_error.code} - {actual_error.message}"
                )
                outcome["error"] = f"A2A Error: {actual_error.code} - {actual_error.message}"
                
            elif isinstance(root_response_part, SendMessageSuccessResponse):
                task_result: A2ATask = root_response_part.result
                business_logger.info(
                    f"Lead Finder task {task_result.id} completed with state: {task_result.status.state}"
                )
                
                # Extract business data from artifacts
                if task_result.artifacts:
                    lead_results_artifact = next(
                        (
                            a
                            for a in task_result.artifacts
                            if a.name == config.DEFAULT_LEAD_FINDER_ARTIFACT_NAME
                        ),
                        None,
                    )
                    
                    if lead_results_artifact and lead_results_artifact.parts:
                        art_part_root = lead_results_artifact.parts[0].root
                        if isinstance(art_part_root, A2ADataPart):
                            result_data = art_part_root.data
                            business_logger.info(f"Extracted Lead Results: {result_data}")
                            
                            if isinstance(result_data, dict) and "businesses" in result_data:
                                outcome["success"] = True
                                outcome["businesses"] = result_data["businesses"]
                            else:
                                business_logger.warning("Unexpected lead results format")
                                outcome["error"] = "Invalid lead results format"
                        else:
                            business_logger.warning(f"Unexpected artifact part type: {type(art_part_root)}")
                    else:
                        business_logger.info("Lead results artifact not found or empty - checking for empty results")
                        # Don't set this as an error immediately, let the success flow handle empty results
                        outcome["success"] = True
                        outcome["businesses"] = []
                else:
                    business_logger.info("No artifacts found in Lead Finder response - treating as empty results")
                    outcome["success"] = True
                    outcome["businesses"] = []
            else:
                business_logger.error(f"Invalid A2A response type: {type(root_response_part)}")
                outcome["error"] = "Invalid response type"
                
    except Exception as e:
        if A2A_AVAILABLE and 'A2AClientHTTPError' in str(type(e)):
            business_logger.error(f"HTTP Error calling Lead Finder: {e}")
            outcome["error"] = f"Connection Error: {e}"
        elif A2A_AVAILABLE and 'A2AClientJSONError' in str(type(e)):
            business_logger.error(f"JSON Error from Lead Finder: {e}")
            outcome["error"] = f"JSON Response Error: {e}"
        else:
            business_logger.error(f"Unexpected error calling Lead Finder: {e}", exc_info=True)
            outcome["error"] = f"Unexpected error: {e}"
    
    return outcome

async def call_lead_finder_agent_simple(city: str, session_id: str) -> dict[str, Any]:
    """
    Calls the Lead Finder service via simple HTTP POST when A2A is not available.
    """
    business_logger = logging.getLogger(BUSINESS_LOGIC_LOGGER)
    
    lead_finder_url = os.environ.get(
        "LEAD_FINDER_SERVICE_URL", config.DEFAULT_LEAD_FINDER_URL
    ).rstrip("/")
    
    business_logger.info(f"Calling Lead Finder (simple HTTP) at {lead_finder_url} for city: {city}")
    
    outcome = {
        "success": False,
        "businesses": [],
        "error": None,
    }
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            # Try different endpoints that might exist
            endpoints_to_try = [
                f"{lead_finder_url}/find_leads",
                f"{lead_finder_url}/search",
                f"{lead_finder_url}/",
            ]
            
            search_data = {
                "city": city,
                "max_results": 50,
                "session_id": session_id,
            }
            
            for endpoint in endpoints_to_try:
                try:
                    business_logger.info(f"Trying endpoint: {endpoint}")
                    response = await client.post(endpoint, json=search_data)
                    
                    if response.status_code == 200:
                        result_data = response.json()
                        business_logger.info(f"Got response from {endpoint}: {result_data}")
                        
                        # Handle different response formats
                        if isinstance(result_data, dict):
                            if "businesses" in result_data:
                                outcome["success"] = True
                                outcome["businesses"] = result_data["businesses"]
                                break
                            elif "results" in result_data:
                                outcome["success"] = True
                                outcome["businesses"] = result_data["results"]
                                break
                            elif "data" in result_data:
                                outcome["success"] = True
                                outcome["businesses"] = result_data["data"]
                                break
                        elif isinstance(result_data, list):
                            outcome["success"] = True
                            outcome["businesses"] = result_data
                            break
                    
                    business_logger.warning(f"Endpoint {endpoint} returned status {response.status_code}")
                    
                except Exception as e:
                    business_logger.warning(f"Endpoint {endpoint} failed: {e}")
                    continue
            
            if not outcome["success"]:
                outcome["error"] = "All Lead Finder endpoints failed or returned no data"
                
    except Exception as e:
        business_logger.error(f"Unexpected error calling Lead Finder: {e}", exc_info=True)
        outcome["error"] = f"Unexpected error: {e}"
    
    return outcome

async def call_lead_finder_agent(city: str, session_id: str) -> dict[str, Any]:
    """
    Calls the Lead Finder agent - uses A2A if available, otherwise falls back to simple HTTP.
    """
    if A2A_AVAILABLE:
        return await call_lead_finder_agent_a2a(city, session_id)
    else:
        return await call_lead_finder_agent_simple(city, session_id)

async def call_sdr_agent_a2a(business_data: dict[str, Any], session_id: str) -> dict[str, Any]:
    """
    Calls the SDR agent via A2A to process a business lead.
    """
    business_logger = logging.getLogger(BUSINESS_LOGIC_LOGGER)
    
    sdr_url = os.environ.get(
        "SDR_SERVICE_URL", config.DEFAULT_SDR_URL
    ).rstrip("/")
    
    business_logger.info(f"Calling SDR agent at {sdr_url} for business: {business_data.get('name', 'Unknown')}")
    
    outcome = {
        "success": False,
        "message": None,
        "error": None,
    }
    
    try:
        async with httpx.AsyncClient() as http_client:
            a2a_client = A2AClient(httpx_client=http_client, url=sdr_url)
            
            # Prepare A2A message
            a2a_task_id = f"sdr-engagement-{session_id}-{business_data.get('id', 'unknown')}"
            
            sdk_message = A2AMessage(
                taskId=a2a_task_id,
                contextId=session_id,
                messageId=str(uuid.uuid4()),
                role=A2ARole.user,
                parts=[A2ADataPart(data=business_data)],
                metadata={"operation": "engage_lead", "business_id": business_data.get("id")},
            )
            
            sdk_send_params = MessageSendParams(
                message=sdk_message,
                configuration=MessageSendConfiguration(
                    acceptedOutputModes=["data", "application/json"]
                ),
            )
            
            sdk_request = SendMessageRequest(
                id=str(uuid.uuid4()), params=sdk_send_params
            )
            
            # Send request to SDR agent
            response: SendMessageResponse = await a2a_client.send_message(sdk_request)
            root_response_part = response.root
            
            if isinstance(root_response_part, JSONRPCErrorResponse):
                actual_error = root_response_part.error
                business_logger.error(
                    f"A2A Error from SDR agent: {actual_error.code} - {actual_error.message}"
                )
                outcome["error"] = f"A2A Error: {actual_error.code} - {actual_error.message}"
                
            elif isinstance(root_response_part, SendMessageSuccessResponse):
                task_result: A2ATask = root_response_part.result
                business_logger.info(
                    f"SDR agent task {task_result.id} completed with state: {task_result.status.state}"
                )
                
                outcome["success"] = True
                outcome["message"] = f"SDR agent has started processing {business_data.get('name', 'the business')}"
                
            else:
                business_logger.error(f"Invalid A2A response type: {type(root_response_part)}")
                outcome["error"] = "Invalid response type"
                
    except Exception as e:
        if A2A_AVAILABLE and 'A2AClientHTTPError' in str(type(e)):
            business_logger.error(f"HTTP Error calling SDR agent: {e}")
            outcome["error"] = f"Connection Error: {e}"
        elif A2A_AVAILABLE and 'A2AClientJSONError' in str(type(e)):
            business_logger.error(f"JSON Error from SDR agent: {e}")
            outcome["error"] = f"JSON Response Error: {e}"
        else:
            business_logger.error(f"Unexpected error calling SDR agent: {e}", exc_info=True)
            outcome["error"] = f"Unexpected error: {e}"
    
    return outcome

async def call_sdr_agent_simple(business_data: dict[str, Any], session_id: str) -> dict[str, Any]:
    """
    Calls the SDR agent via simple HTTP POST when A2A is not available.
    """
    business_logger = logging.getLogger(BUSINESS_LOGIC_LOGGER)
    
    sdr_url = os.environ.get(
        "SDR_SERVICE_URL", config.DEFAULT_SDR_URL
    ).rstrip("/")
    
    business_logger.info(f"Calling SDR agent (simple HTTP) at {sdr_url} for business: {business_data.get('name', 'Unknown')}")
    
    outcome = {
        "success": False,
        "message": None,
        "error": None,
    }
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            # Try different endpoints that might exist
            endpoints_to_try = [
                # f"{sdr_url}/engage_lead",
                # f"{sdr_url}/process",
                f"{sdr_url}/",
            ]
            
            sdr_data = {
                "business": business_data,
                "session_id": session_id,
            }
            
            for endpoint in endpoints_to_try:
                try:
                    business_logger.info(f"Trying SDR endpoint: {endpoint}")
                    response = await client.post(endpoint, json=sdr_data)
                    
                    if response.status_code == 200:
                        result_data = response.json()
                        business_logger.info(f"Got response from SDR at {endpoint}: {result_data}")
                        
                        outcome["success"] = True
                        outcome["message"] = f"SDR agent has started processing {business_data.get('name', 'the business')}"
                        break
                    
                    business_logger.warning(f"SDR endpoint {endpoint} returned status {response.status_code}")
                    
                except Exception as e:
                    business_logger.warning(f"SDR endpoint {endpoint} failed: {e}")
                    continue
            
            if not outcome["success"]:
                outcome["error"] = "All SDR agent endpoints failed"
                
    except Exception as e:
        business_logger.error(f"Unexpected error calling SDR agent: {e}", exc_info=True)
        outcome["error"] = f"Unexpected error: {e}"
    
    return outcome

async def call_sdr_agent(business_data: dict[str, Any], session_id: str) -> dict[str, Any]:
    """
    Calls the SDR agent - uses A2A if available, otherwise falls back to simple HTTP.
    """
    if A2A_AVAILABLE:
        return await call_sdr_agent_a2a(business_data, session_id)
    else:
        return await call_sdr_agent_simple(business_data, session_id)

async def call_lead_manager_agent_a2a(query: str, session_id: str) -> dict[str, Any]:
    """
    Calls the Lead Manager agent via A2A to process lead management tasks.
    """
    business_logger = logging.getLogger(BUSINESS_LOGIC_LOGGER)
    
    lead_manager_url = os.environ.get(
        "LEAD_MANAGER_SERVICE_URL", config.DEFAULT_LEAD_MANAGER_URL
    ).rstrip("/")
    
    business_logger.info(f"Calling Lead Manager at {lead_manager_url} for query: {query}")
    
    outcome = {
        "success": False,
        "message": None,
        "error": None,
    }
    
    try:
        async with httpx.AsyncClient() as http_client:
            a2a_client = A2AClient(httpx_client=http_client, url=lead_manager_url)
            
            # Prepare A2A message
            a2a_task_id = f"lead-management-{session_id}"
            
            lead_data = {
                "query": query,
                "ui_client_url": config.DEFAULT_UI_CLIENT_URL
            }
            
            sdk_message = A2AMessage(
                taskId=a2a_task_id,
                contextId=session_id,
                messageId=str(uuid.uuid4()),
                role=A2ARole.user,
                parts=[A2ADataPart(data=lead_data)],
                metadata={"operation": "process_lead_management", "query": query},
            )
            
            sdk_send_params = MessageSendParams(
                message=sdk_message,
                configuration=MessageSendConfiguration(
                    acceptedOutputModes=["data", "application/json"]
                ),
            )
            
            sdk_request = SendMessageRequest(
                id=str(uuid.uuid4()), params=sdk_send_params
            )
            
            # Send request to Lead Manager
            response: SendMessageResponse = await a2a_client.send_message(sdk_request)
            root_response_part = response.root
            
            if isinstance(root_response_part, JSONRPCErrorResponse):
                actual_error = root_response_part.error
                business_logger.error(
                    f"A2A Error from Lead Manager: {actual_error.code} - {actual_error.message}"
                )
                outcome["error"] = f"A2A Error: {actual_error.code} - {actual_error.message}"
                
            elif isinstance(root_response_part, SendMessageSuccessResponse):
                task_result: A2ATask = root_response_part.result
                business_logger.info(
                    f"Lead Manager task {task_result.id} completed with state: {task_result.status.state}"
                )
                
                # Extract result from artifacts
                if task_result.artifacts:
                    lead_management_artifact = next(
                        (
                            a
                            for a in task_result.artifacts
                            if a.name == config.DEFAULT_LEAD_MANAGER_ARTIFACT_NAME
                        ),
                        None,
                    )
                    
                    if lead_management_artifact and lead_management_artifact.parts:
                        art_part_root = lead_management_artifact.parts[0].root
                        if isinstance(art_part_root, A2ADataPart):
                            result_data = art_part_root.data
                            business_logger.info(f"Lead Manager Result: {result_data}")
                            outcome["success"] = True
                            outcome["message"] = result_data.get("message", "Lead management task completed")
                
                if not outcome["success"]:
                    outcome["success"] = True
                    outcome["message"] = "Lead management task completed successfully"
                
            else:
                business_logger.error(f"Invalid A2A response type: {type(root_response_part)}")
                outcome["error"] = "Invalid response type"
                
    except Exception as e:
        business_logger.warning(f"A2A Lead Manager call failed: {e}")
        outcome["error"] = f"A2A call failed: {e}"
    
    return outcome

async def call_lead_manager_agent_simple(query: str, session_id: str) -> dict[str, Any]:
    """
    Calls the Lead Manager service via simple HTTP POST when A2A is not available.
    """
    business_logger = logging.getLogger(BUSINESS_LOGIC_LOGGER)
    
    lead_manager_url = os.environ.get(
        "LEAD_MANAGER_SERVICE_URL", config.DEFAULT_LEAD_MANAGER_URL
    ).rstrip("/")
    
    business_logger.info(f"Calling Lead Manager (simple) at {lead_manager_url} for query: {query}")
    
    outcome = {
        "success": False,
        "message": None,
        "error": None,
    }
    
    try:
        async with httpx.AsyncClient() as http_client:
            payload = {
                "query": query,
                "ui_client_url": config.DEFAULT_UI_CLIENT_URL
            }
            
            response = await http_client.post(
                f"{lead_manager_url}/search",
                json=payload,
                timeout=30.0
            )
            
            if response.status_code == 200:
                result = response.json()
                business_logger.info(f"Lead Manager (simple) responded: {result}")
                outcome["success"] = True
                outcome["message"] = result.get("message", "Lead management completed successfully")
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                business_logger.error(f"Lead Manager (simple) error: {error_msg}")
                outcome["error"] = error_msg
                
    except Exception as e:
        business_logger.error(f"Unexpected error calling Lead Manager (simple): {e}", exc_info=True)
        outcome["error"] = f"Unexpected error: {e}"
    
    return outcome

async def call_lead_manager_agent(query: str, session_id: str) -> dict[str, Any]:
    """
    Calls the Lead Manager agent - uses A2A if available, otherwise falls back to simple HTTP.
    """
    if A2A_AVAILABLE:
        try:
            return await call_lead_manager_agent_a2a(query, session_id)
        except Exception as e:
            business_logger = logging.getLogger(BUSINESS_LOGIC_LOGGER)
            business_logger.warning(f"A2A call failed, falling back to simple HTTP: {e}")
            return await call_lead_manager_agent_simple(query, session_id)
    else:
        return await call_lead_manager_agent_simple(query, session_id)

async def run_lead_finding_process(city: str, session_id: str):
    """
    Run the lead finding process - finds businesses WITHOUT websites.
    These are prime leads for web development services.
    Limited to 20 results at a time.
    """
    business_logger = logging.getLogger(BUSINESS_LOGIC_LOGGER)
    MAX_LEADS = 20  # Limit as requested
    
    try:
        business_logger.info(f"Starting lead finding for {city} (max {MAX_LEADS} leads)")
        
        found_businesses = []
        
        # PRIMARY: Use direct Google Maps search for fast, reliable results
        # This finds businesses WITHOUT websites - prime leads for web development
        if DIRECT_SEARCH_AVAILABLE:
            business_logger.info("Using direct Google Maps search (finds businesses without websites)...")
            try:
                result = await direct_search_businesses(city, max_results=MAX_LEADS)
                if result.get("success") and result.get("businesses"):
                    found_businesses = result["businesses"][:MAX_LEADS]
                    business_logger.info(f"Direct search found {len(found_businesses)} leads without websites")
            except Exception as e:
                business_logger.warning(f"Direct search failed: {e}")
        
        # FALLBACK: Try the agent-based approach if direct search failed
        if not found_businesses:
            business_logger.info("Direct search returned no results, trying Lead Finder agent...")
            try:
                result = await call_lead_finder_agent(city, session_id)
                if result.get("success"):
                    found_businesses = result.get("businesses", [])[:MAX_LEADS]
                    business_logger.info(f"Agent found {len(found_businesses)} businesses")
            except Exception as agent_error:
                business_logger.warning(f"Agent fallback failed: {agent_error}")
        
        # Process found businesses and add to UI
        if found_businesses:
            business_logger.info(f"Processing {len(found_businesses)} leads for UI")
            
            for biz_data in found_businesses:
                try:
                    # Create Business object with comprehensive data
                    business_id = biz_data.get("id") or biz_data.get("place_id") or str(uuid.uuid4())
                    
                    # Build description from available data
                    desc_parts = []
                    if biz_data.get("category"):
                        desc_parts.append(biz_data["category"].replace("_", " ").title())
                    if biz_data.get("rating"):
                        desc_parts.append(f"Rating: {biz_data['rating']}⭐")
                    if biz_data.get("review_count"):
                        desc_parts.append(f"({biz_data['review_count']} reviews)")
                    description = " | ".join(desc_parts) if desc_parts else "Local Business"
                    
                    business = Business(
                        id=business_id,
                        name=biz_data.get("name", "Unknown Business"),
                        phone=biz_data.get("phone", ""),
                        email=biz_data.get("email", ""),
                        city=biz_data.get("city", city),
                        description=description,
                        status=BusinessStatus.FOUND,
                    )
                    
                    # Add to app state
                    app_state["businesses"][business.id] = business
                    
                    # Send real-time update to UI via WebSocket
                    await manager.send_update({
                        "type": "business_added",
                        "agent": "lead_finder",
                        "business": business.model_dump(),
                        "timestamp": datetime.now().isoformat(),
                    })
                    
                    business_logger.info(f"Added lead: {business.name} (no website)")
                    
                except Exception as e:
                    business_logger.warning(f"Failed to process business {biz_data.get('name')}: {e}")
                    continue
            
            # Send completion update
            await manager.send_update({
                "type": "lead_finding_completed",
                "city": city,
                "business_count": len(app_state["businesses"]),
                "timestamp": datetime.now().isoformat(),
            })
            
            business_logger.info(f"✓ Lead finding complete: {len(app_state['businesses'])} leads in {city}")
        else:
            business_logger.info(f"No businesses without websites found in {city}")
            await manager.send_update({
                "type": "lead_finding_empty",
                "city": city,
                "message": "No businesses without websites found. Try another city.",
                "timestamp": datetime.now().isoformat(),
            })
    
    except Exception as e:
        business_logger.error(f"Error in lead finding process: {e}", exc_info=True)
        await manager.send_update({
            "type": "lead_finding_failed",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        })
    
    finally:
        app_state["is_running"] = False
        await manager.send_update({
            "type": "process_finished",
            "timestamp": datetime.now().isoformat(),
        })

# WebSocket endpoint for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send current state to newly connected client
        await websocket.send_text(json.dumps({
            "type": "initial_state",
            "businesses": [business.dict() for business in app_state["businesses"].values()],
            "current_city": app_state["current_city"],
            "is_running": app_state["is_running"],
        }, default=str))
        
        # Keep connection alive
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Agent callback endpoint
# In ui_client/main.py
# In ui_client/main.py

# In ui_client/main.py

# In ui_client/main.py

@app.post("/agent_callback")
async def agent_callback(update: AgentUpdate):
    """
    Endpoint for agents to send updates about business processing.
    This version handles creating new businesses and correctly serializes
    Pydantic models before sending them over WebSockets.
    """
    logger.info(f"Received agent callback: {update.agent_type} for business {update.business_id}")

    # Special handling for Calendar agent: do not auto-create businesses, only send meeting notifications
    if update.agent_type == AgentType.CALENDAR:
        # If the business exists, update its status and send business_updated event
        if update.business_id in app_state["businesses"]:
            business = app_state["businesses"][update.business_id]
            business.status = update.status
            business.updated_at = datetime.now()
            business.notes.append(f"{update.agent_type}: {update.message}")
            logger.info(f"Updated business {business.name} status to {update.status}")
            biz_payload = {
                "type": "business_updated",
                "agent": update.agent_type.value,
                "business": business.model_dump(),
                "update": update.model_dump(),
                "timestamp": datetime.now().isoformat(),
            }
            await manager.send_update(biz_payload)
        # Always send the calendar-specific notification
        cal_payload = {
            "type": "calendar_notification",
            "agent": update.agent_type.value,
            "business_id": update.business_id,
            "data": update.data or {},
            "message": update.message,
            "timestamp": datetime.now().isoformat(),
        }
        await manager.send_update(cal_payload)
        return JSONResponse(status_code=200, content={"status": "success", "message": "Calendar notification sent"})
    # Check if business exists for non-calendar agents
    if update.business_id in app_state["businesses"]:
        # Business exists, so update it
        business = app_state["businesses"][update.business_id]
        business.status = update.status
        business.updated_at = datetime.now()
        business.notes.append(f"{update.agent_type}: {update.message}")
        logger.info(f"Updated business {business.name} status to {update.status}")
    else:
        # Business does NOT exist, attempt to create a new entry with available data
        logger.info(f"Business ID {update.business_id} not found. Attempting to create new business entry.")
        data = update.data or {}
        # Fallback fields from various possible keys
        name = data.get("name") or data.get("sender_name") or data.get("lead_name")
        city = data.get("city") or ""
        phone = data.get("phone") or data.get("lead_phone") or data.get("phone_number")
        email = data.get("email") or data.get("sender_email") or data.get("lead_email")
        description = (
            data.get("description") or data.get("subject") or data.get("email_subject") or data.get("body_preview")
        )
        if not name:
            logger.warning(f"Cannot create business {update.business_id}: missing name in callback data.")
            return JSONResponse(status_code=400, content={"status": "error", "message": "Cannot create business: missing name"})
        try:
            new_business = Business(
                id=update.business_id,
                name=name,
                phone=phone,
                email=email,
                description=description,
                city=city,
                status=update.status,
                notes=[f"{update.agent_type}: {update.message}"]
            )
            app_state["businesses"][update.business_id] = new_business
        except Exception as e:
            logger.error(f"Failed to create business from callback data: {e}")
            return JSONResponse(status_code=400, content={"status": "error", "message": f"Cannot create business: {str(e)}"})

    # Get the final business object to send in the update
    final_business_obj = app_state["businesses"].get(update.business_id)
    # Handle calendar events: first send a business_updated to move/create the card,
    # then send a calendar_notification with meeting details
    if update.agent_type == AgentType.CALENDAR and final_business_obj:
        # Business_updated event for calendar status
        biz_payload = {
            "type": "business_updated",
            "agent": update.agent_type.value,
            "business": final_business_obj.model_dump(),
            "update": update.model_dump(),
            "timestamp": datetime.now().isoformat(),
        }
        await manager.send_update(biz_payload)
        # Calendar-specific notification
        cal_payload = {
            "type": "calendar_notification",
            "agent": update.agent_type.value,
            "business_id": update.business_id,
            "data": update.data,
            "message": update.message,
            "timestamp": datetime.now().isoformat(),
        }
        await manager.send_update(cal_payload)
    # Handle other agent updates
    elif final_business_obj:
        # Standard business update: store and notify
        app_state["agent_updates"].append(update)
        update_payload = {
            "type": "business_updated",
            "agent": update.agent_type.value,
            "business": final_business_obj.model_dump(),
            "update": update.model_dump(),
            "timestamp": datetime.now().isoformat(),
        }
        await manager.send_update(update_payload)

    return JSONResponse(status_code=200, content={"status": "success", "message": "Business processed"})


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request) -> HTMLResponse:
    """Serves the landing page — the first thing every visitor sees."""
    response = templates.TemplateResponse(
        name="landing.html",
        context={
            "request": request,
            "clerk_publishable_key": CLERK_PUBLISHABLE_KEY
        }
    )
    # Add cache control headers to force refresh
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request) -> HTMLResponse:
    """Serves the city search / input page (requires auth via Clerk on client)."""
    response = templates.TemplateResponse(
        name="search.html",
        context={
            "request": request,
            "clerk_publishable_key": CLERK_PUBLISHABLE_KEY
        }
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """Serves the dashboard with lead data."""
    response = templates.TemplateResponse(
        name="dashboard.html",
        context={
            "request": request,
            "businesses": list(app_state["businesses"].values()),
            "current_city": app_state["current_city"],
            "is_running": app_state["is_running"],
            "agent_updates": app_state["agent_updates"][-20:],
            "clerk_publishable_key": CLERK_PUBLISHABLE_KEY
        }
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/architecture_diagram", response_class=HTMLResponse)
async def architecture_diagram(request: Request) -> HTMLResponse:
    """Serves the architecture diagram page."""
    return templates.TemplateResponse(
        name="architecture_diagram.html",
        context={
            "request": request
        }
    )


# ============================================
# USER PROFILE & LEADS DASHBOARD
# ============================================

@app.get("/profile", response_class=HTMLResponse)
async def user_profile_page(request: Request) -> HTMLResponse:
    """Serves the user profile and leads dashboard page."""
    response = templates.TemplateResponse(
        name="profile.html",
        context={
            "request": request,
            "clerk_publishable_key": CLERK_PUBLISHABLE_KEY
        }
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.get("/history", response_class=HTMLResponse)
async def lead_history_page(request: Request) -> HTMLResponse:
    """Serves the lead history and analytics page."""
    response = templates.TemplateResponse(
        name="history.html",
        context={
            "request": request,
            "clerk_publishable_key": CLERK_PUBLISHABLE_KEY
        }
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.get("/api/user/stats")
async def get_user_stats_api(request: Request) -> JSONResponse:
    """Get current user's lead statistics from Firebase."""
    if not FIREBASE_AVAILABLE:
        return JSONResponse(content={"success": False, "error": "Firebase not available"})
    
    try:
        user_id = "anonymous"
        if AUTH_AVAILABLE:
            user = await get_current_user(request)
            if user:
                user_id = user.get("sub", "anonymous")
        
        fb_service = get_firebase_service()
        if not fb_service.is_available():
            return JSONResponse(content={"success": False, "error": "Firebase not initialized"})
        
        stats = await fb_service.get_user_stats(user_id)
        
        # Also get user profile for member_since and login_count
        profile = await fb_service.get_user_profile(user_id)
        if profile:
            if profile.get("created_at"):
                stats["member_since"] = profile["created_at"]
            if profile.get("login_count"):
                stats["login_count"] = profile["login_count"]
        
        return JSONResponse(content={"success": True, "stats": stats})
    except Exception as e:
        logger.error(f"Failed to get user stats: {e}")
        return JSONResponse(content={"success": False, "error": str(e)})


@app.get("/api/user/profile")
async def get_user_profile_api(request: Request) -> JSONResponse:
    """Get current user's profile from Firebase."""
    if not FIREBASE_AVAILABLE:
        return JSONResponse(content={"success": False, "error": "Firebase not available"})
    
    try:
        user_id = "anonymous"
        if AUTH_AVAILABLE:
            user = await get_current_user(request)
            if user:
                user_id = user.get("sub", "anonymous")
        
        fb_service = get_firebase_service()
        if not fb_service.is_available():
            return JSONResponse(content={"success": False, "error": "Firebase not initialized"})
        
        profile = await fb_service.get_user_profile(user_id)
        return JSONResponse(content={"success": True, "profile": profile or {}})
    except Exception as e:
        logger.error(f"Failed to get user profile: {e}")
        return JSONResponse(content={"success": False, "error": str(e)})


# ============================================
# AUTHENTICATION ROUTES (Clerk Integration)
# ============================================

@app.get("/auth/login", response_class=HTMLResponse)
async def auth_login(request: Request) -> HTMLResponse:
    """Serves the login page with Clerk authentication."""
    return templates.TemplateResponse(
        name="login.html",
        context={
            "request": request,
            "clerk_publishable_key": CLERK_PUBLISHABLE_KEY
        }
    )


@app.get("/auth/signup", response_class=HTMLResponse)
async def auth_signup(request: Request) -> HTMLResponse:
    """Serves the signup page with Clerk authentication."""
    return templates.TemplateResponse(
        name="signup.html",
        context={
            "request": request,
            "clerk_publishable_key": CLERK_PUBLISHABLE_KEY
        }
    )


@app.get("/auth/logout")
async def auth_logout(request: Request) -> RedirectResponse:
    """Handles logout by redirecting to home (Clerk handles session on client)."""
    response = RedirectResponse(url="/", status_code=302)
    # Clear any server-side session cookies if present
    response.delete_cookie("__session")
    response.delete_cookie("__clerk_db_jwt")
    return response


@app.get("/api/auth/user")
async def get_user_api(request: Request) -> JSONResponse:
    """API endpoint to get current user info."""
    if AUTH_AVAILABLE:
        user = await get_current_user(request)
        if user:
            auth_state = AuthState(user)
            
            # Track user sign-in to Firebase
            if FIREBASE_AVAILABLE:
                try:
                    fb_service = get_firebase_service()
                    if fb_service.is_available():
                        user_agent = request.headers.get("user-agent", "unknown")
                        ip_address = request.client.host if request.client else "unknown"
                        await fb_service.track_user_signin(
                            user_id=user.get("sub", "anonymous"),
                            email=user.get("email"),
                            name=user.get("name"),
                            picture=user.get("picture"),
                            ip_address=ip_address,
                            user_agent=user_agent
                        )
                except Exception as e:
                    logger.warning(f"Failed to track user sign-in: {e}")
            
            return JSONResponse(content={
                "authenticated": True,
                "user": auth_state.to_dict()
            })
    
    return JSONResponse(content={
        "authenticated": False,
        "user": None
    })


@app.get("/api/auth/verify")
async def verify_auth(request: Request) -> JSONResponse:
    """Verify if the current session is authenticated."""
    if AUTH_AVAILABLE:
        user = await get_current_user(request)
        return JSONResponse(content={
            "authenticated": user is not None,
            "user_id": user.get("sub") if user else None
        })
    
    return JSONResponse(content={
        "authenticated": False,
        "message": "Auth module not available"
    })


@app.get("/test_ui", response_class=HTMLResponse)
async def test_ui(request: Request) -> HTMLResponse:
    """Test page to verify UI update."""
    response = templates.TemplateResponse(
        name="test_ui.html",
        context={
            "request": request
        }
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
        
        
@app.post("/start_lead_finding")
async def start_lead_finding(city: str = Form(...)):
    """Start the lead finding process for a given city."""
    if app_state["is_running"]:
        return JSONResponse(
            status_code=400,
            content={"error": "Lead finding process is already running"}
        )
    
    try:
        # Validate input
        request_data = LeadFinderRequest(city=city.strip())
        
        app_state["is_running"] = True
        app_state["current_city"] = request_data.city
        app_state["session_id"] = str(uuid.uuid4())
        app_state["businesses"] = {}  # Reset businesses for new search
        app_state["agent_updates"] = []  # Reset updates
        
        logger.info(f"Starting lead finding process for city: {request_data.city}")
        
        # Send initial update
        await manager.send_update({
            "type": "process_started",
            "city": request_data.city,
            "timestamp": datetime.now().isoformat(),
        })
        
        # Call Lead Finder agent asynchronously
        asyncio.create_task(run_lead_finding_process(request_data.city, app_state["session_id"]))
        
        return RedirectResponse("/dashboard", status_code=303)
        
    except ValidationError as e:
        logger.error(f"Invalid city input: {e}")
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid input: {e}"}
        )
    except Exception as e:
        logger.error(f"Error starting lead finding: {e}", exc_info=True)
        app_state["is_running"] = False
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to start process: {e}"}
        )


@app.get("/api/businesses")
async def get_businesses():
    """API endpoint to get all businesses."""
    return {
        "businesses": [business.dict() for business in app_state["businesses"].values()],
        "total": len(app_state["businesses"])
    }

@app.get("/api/leads/history")
async def get_leads_history(request: Request, status: Optional[str] = None):
    """
    API endpoint to get persisted lead history from Firebase.
    Returns leads for the current authenticated user.
    """
    if not BIGQUERY_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error": "Firebase service not available"}
        )
    
    try:
        # Get current user
        user_id = "anonymous"
        if AUTH_AVAILABLE:
            user = await get_current_user(request)
            if user:
                user_id = user.get("sub", "anonymous")
        
        # Query Firebase
        fb_service = get_firebase_service()
        if not fb_service.is_available():
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "Firebase client not initialized"}
            )
        
        # Convert status string to enum if provided
        status_filter = None
        if status:
            try:
                status_filter = LeadStatus(status.upper())
            except ValueError:
                pass
        
        leads = await fb_service.get_leads_by_user(user_id, status_filter)
        
        return {
            "success": True,
            "user_id": user_id,
            "leads": leads,
            "total": len(leads),
            "status_filter": status
        }
        
    except Exception as e:
        logger.error(f"Failed to fetch lead history: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.get("/api/leads/{lead_id}")
async def get_lead_details(lead_id: str, request: Request):
    """
    API endpoint to get full details for a specific lead.
    Returns all lead data including meeting info and notes.
    """
    if not BIGQUERY_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error": "Firebase service not available"}
        )
    
    try:
        # Get current user
        user_id = "anonymous"
        if AUTH_AVAILABLE:
            user = await get_current_user(request)
            if user:
                user_id = user.get("sub", "anonymous")
        
        lead_data = await get_lead_full_details(lead_id)
        
        if not lead_data:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Lead not found"}
            )
        
        # Verify the lead belongs to this user (or is anonymous)
        lead_user = lead_data.get("user_id", "anonymous")
        if lead_user != "anonymous" and lead_user != user_id:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Access denied"}
            )
        
        return {"success": True, "lead": lead_data}
        
    except Exception as e:
        logger.error(f"Failed to fetch lead details: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.post("/api/leads/{lead_id}/confirm")
async def confirm_lead_final(lead_id: str, request: Request):
    """
    API endpoint to mark a lead as CONFIRMED (final status).
    This is the last stage of the lead lifecycle.
    """
    if not BIGQUERY_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error": "Firebase service not available"}
        )
    
    try:
        # Get current user
        user_info = {}
        if AUTH_AVAILABLE:
            user = await get_current_user(request)
            if user:
                user_info = {
                    "user_id": user.get("sub", "anonymous"),
                    "email": user.get("email"),
                    "name": user.get("name"),
                }
        
        # Parse optional note from request body
        note = None
        try:
            body = await request.json()
            note = body.get("note")
        except Exception:
            pass
        
        result = await persist_lead_confirmed(lead_id, user_info, note)
        
        if result.get("success"):
            logger.info(f"✅ Lead {lead_id} confirmed (final status)")
            return {"success": True, "lead_id": lead_id, "status": "CONFIRMED"}
        else:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": result.get("error", "Failed to confirm lead")}
            )
        
    except Exception as e:
        logger.error(f"Failed to confirm lead: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.post("/api/leads/{lead_id}/add_note")
async def add_lead_note(lead_id: str, request: Request):
    """
    API endpoint to add a note to a lead.
    """
    if not BIGQUERY_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error": "Firebase service not available"}
        )
    
    try:
        # Get current user
        user_info = {}
        if AUTH_AVAILABLE:
            user = await get_current_user(request)
            if user:
                user_info = {
                    "user_id": user.get("sub", "anonymous"),
                    "email": user.get("email"),
                    "name": user.get("name"),
                }
        
        # Parse note from request body
        try:
            body = await request.json()
            note = body.get("note")
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Invalid request body"}
            )
        
        if not note or not note.strip():
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Note cannot be empty"}
            )
        
        result = await add_note_to_lead(lead_id, note.strip(), user_info)
        
        if result.get("success"):
            logger.info(f"✅ Note added to lead {lead_id}")
            return {"success": True, "lead_id": lead_id}
        else:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": result.get("error", "Failed to add note")}
            )
        
    except Exception as e:
        logger.error(f"Failed to add note to lead: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.post("/api/leads/{lead_id}/update_status")
async def update_lead_status(lead_id: str, request: Request):
    """
    API endpoint to update lead status based on dashboard column.
    Call this when a lead is moved to a different column.
    """
    if not BIGQUERY_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error": "Firebase service not available"}
        )
    
    try:
        # Get current user
        user_info = {}
        if AUTH_AVAILABLE:
            user = await get_current_user(request)
            if user:
                user_info = {
                    "user_id": user.get("sub", "anonymous"),
                    "email": user.get("email"),
                    "name": user.get("name"),
                }
        
        # Parse status from request body
        try:
            body = await request.json()
            column_status = body.get("status") or body.get("column_status")
            lead_details = body.get("lead_details")
            meeting_details = body.get("meeting_details")
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Invalid request body"}
            )
        
        if not column_status:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Status is required"}
            )
        
        result = await update_lead_status_by_column(
            lead_id=lead_id,
            column_status=column_status,
            user_info=user_info,
            lead_details=lead_details,
            meeting_details=meeting_details
        )
        
        if result.get("success"):
            logger.info(f"✅ Lead {lead_id} status updated to {result.get('status')}")
            return {"success": True, "lead_id": lead_id, "status": result.get("status")}
        else:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": result.get("error", "Failed to update status")}
            )
        
    except Exception as e:
        logger.error(f"Failed to update lead status: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.get("/api/status")
async def get_status():
    """API endpoint to get current application status."""
    return {
        "is_running": app_state["is_running"],
        "current_city": app_state["current_city"],
        "business_count": len(app_state["businesses"]),
        "session_id": app_state["session_id"],
    }

@app.post("/send_to_sdr")
async def send_business_to_sdr(
    request: Request,
    business_id: str = Form(...), 
    user_phone: Optional[str] = Form(None)
):
    """
    Send a business to the SDR agent for processing.
    Uses local AI-powered research and proposal generation.
    """
    try:
        # Check if business exists
        if business_id not in app_state["businesses"]:
            return JSONResponse(
                status_code=404,
                content={"error": "Business not found"}
            )
        
        business = app_state["businesses"][business_id]
        
        # Check if SDR research module is available
        if not SDR_RESEARCH_AVAILABLE:
            return JSONResponse(
                status_code=503,
                content={"error": "SDR Research module not available. Please check API configuration."}
            )
        
        # Convert business to dict for processing
        business_data = business.model_dump()
        
        # Override phone number if user provided one (optional)
        if user_phone:
            business_data["phone_number"] = user_phone
            business_data["phone"] = user_phone
            logger.info(f"Using provided phone number: {user_phone} for business {business.name}")
        
        logger.info(f"Starting SDR processing for {business.name}")
        
        # Send initial update via WebSocket
        await manager.send_update({
            "type": "sdr_processing",
            "business_id": business_id,
            "business_name": business.name,
            "message": f"SDR Agent is researching {business.name}...",
            "timestamp": datetime.now().isoformat(),
        })
        
        # Step 1: Research the business using AI
        research_result = await research_business(business_data)
        
        if not research_result["success"]:
            logger.error(f"Research failed for {business.name}: {research_result.get('error')}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Research failed: {research_result.get('error', 'Unknown error')}"}
            )
        
        research_data = research_result["research"]
        
        # Send research complete update
        await manager.send_update({
            "type": "sdr_research_complete",
            "business_id": business_id,
            "business_name": business.name,
            "message": f"Research complete. Generating proposal for {business.name}...",
            "timestamp": datetime.now().isoformat(),
        })
        
        # Step 2: Generate a sales proposal based on research
        proposal_result = await generate_proposal(business_data, research_data)
        
        if not proposal_result["success"]:
            logger.warning(f"Proposal generation failed for {business.name}, but research succeeded")
            # Still return success with just research data
            await manager.send_update({
                "type": "sdr_engaged",
                "business_id": business_id,
                "business_name": business.name,
                "message": f"SDR Agent completed research for {business.name}",
                "research": research_data,
                "proposal": None,
                "timestamp": datetime.now().isoformat(),
            })
            
            # Persist to Firebase even when proposal fails - research still succeeded
            if BIGQUERY_AVAILABLE:
                try:
                    user_info = {}
                    if AUTH_AVAILABLE:
                        try:
                            user = await get_current_user(request)
                            user_info = {
                                "user_id": user.get("sub", "anonymous") if user else "anonymous",
                                "email": user.get("email") if user else None,
                                "name": user.get("name") if user else None,
                            }
                        except Exception:
                            pass
                    bq_result = await persist_sdr_engaged(
                        lead_id=business_id,
                        user_info=user_info,
                        lead_details=business_data,
                        research_data=research_data,
                    )
                    if bq_result.get("success"):
                        logger.info(f"✅ Lead {business.name} persisted to Firebase (SDR_ENGAGED, no proposal)")
                    elif not bq_result.get("skipped"):
                        logger.error(f"❌ Firebase SDR_ENGAGED failed: {bq_result.get('error')}")
                except Exception as bq_error:
                    logger.error(f"❌ Firebase persistence exception: {bq_error}")
            
            return JSONResponse(
                status_code=200,
                content={
                    "success": True, 
                    "message": f"SDR Agent completed research for {business.name}. Proposal generation is pending.",
                    "research": research_data,
                    "proposal": None
                }
            )
        
        proposal_text = proposal_result["proposal"]
        
        # Store the SDR result in app state for future reference
        if "sdr_results" not in app_state:
            app_state["sdr_results"] = {}
        
        app_state["sdr_results"][business_id] = {
            "business": business_data,
            "research": research_data,
            "proposal": proposal_text,
            "timestamp": datetime.now().isoformat(),
            "status": "completed"
        }
        
        # Send success update via WebSocket with full results
        await manager.send_update({
            "type": "sdr_engaged",
            "business_id": business_id,
            "business_name": business.name,
            "message": f"SDR Agent completed analysis and proposal for {business.name}",
            "research": research_data,
            "proposal": proposal_text,
            "timestamp": datetime.now().isoformat(),
        })
        
        logger.info(f"SDR Agent successfully processed {business.name}")
        
        # Persist to Firebase if available - SDR engaged is first lifecycle stage
        if BIGQUERY_AVAILABLE:
            try:
                user_info = {}
                if AUTH_AVAILABLE:
                    try:
                        user = await get_current_user(request)
                        user_info = {
                            "user_id": user.get("sub", "anonymous") if user else "anonymous",
                            "email": user.get("email") if user else None,
                            "name": user.get("name") if user else None,
                        }
                    except Exception as auth_err:
                        logger.warning(f"Could not get user for Firebase: {auth_err}")
                
                bq_result = await persist_sdr_engaged(
                    lead_id=business_id,
                    user_info=user_info,
                    lead_details=business_data,
                    research_data=research_data,
                )
                
                if bq_result.get("success"):
                    logger.info(f"✅ Lead {business.name} persisted to Firebase (SDR_ENGAGED)")
                elif not bq_result.get("skipped"):
                    logger.error(f"❌ Firebase SDR_ENGAGED failed: {bq_result.get('error')}")
            except Exception as bq_error:
                logger.error(f"❌ Firebase persistence exception: {bq_error}", exc_info=True)
        else:
            logger.info("⏭️ Firebase not available, SDR engagement not persisted")
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True, 
                "message": f"SDR Agent completed research and generated proposal for {business.name}",
                "research": research_data,
                "proposal": proposal_text
            }
        )
            
    except Exception as e:
        logger.error(f"Error in SDR processing for business: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to process with SDR: {str(e)}"}
        )


@app.get("/research_business/{business_id}")
async def research_business_endpoint(business_id: str):
    """
    Research a specific business using AI to gather insights.
    Returns detailed analysis including pain points, opportunities, and recommendations.
    """
    try:
        # Check if business exists
        if business_id not in app_state["businesses"]:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Business not found"}
            )
        
        business = app_state["businesses"][business_id]
        
        # Check if SDR research module is available
        if not SDR_RESEARCH_AVAILABLE:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "SDR Research module not available"}
            )
        
        # Convert business to dict for research
        business_data = business.model_dump()
        
        logger.info(f"Starting AI research for business: {business.name}")
        
        # Send initial update via WebSocket
        await manager.send_update({
            "type": "research_started",
            "business_id": business_id,
            "business_name": business.name,
            "message": f"Starting AI research for {business.name}...",
            "timestamp": datetime.now().isoformat(),
        })
        
        # Call the research function
        result = await research_business(business_data)
        
        if result["success"]:
            # Send success update via WebSocket
            await manager.send_update({
                "type": "research_completed",
                "business_id": business_id,
                "business_name": business.name,
                "message": f"Research completed for {business.name}",
                "timestamp": datetime.now().isoformat(),
            })
            
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "business_id": business_id,
                    "business_name": business.name,
                    "research": result["research"],
                    "business_info": result.get("business_info", {})
                }
            )
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": result["error"]}
            )
            
    except Exception as e:
        logger.error(f"Error researching business: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Research failed: {e}"}
        )


@app.post("/generate_proposal/{business_id}")
async def generate_proposal_endpoint(business_id: str):
    """
    Generate a sales proposal for a specific business based on research.
    """
    try:
        # Check if business exists
        if business_id not in app_state["businesses"]:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Business not found"}
            )
        
        business = app_state["businesses"][business_id]
        business_data = business.model_dump()
        
        # Check if SDR research module is available
        if not SDR_RESEARCH_AVAILABLE:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "SDR Research module not available"}
            )
        
        # First, research the business
        research_result = await research_business(business_data)
        
        if not research_result["success"]:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": research_result["error"]}
            )
        
        # Generate the proposal
        proposal_result = await generate_proposal(business_data, research_result["research"])
        
        if proposal_result["success"]:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "business_id": business_id,
                    "business_name": business.name,
                    "proposal": proposal_result["proposal"],
                    "research": research_result["research"]
                }
            )
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": proposal_result["error"]}
            )
            
    except Exception as e:
        logger.error(f"Error generating proposal: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Proposal generation failed: {e}"}
        )


@app.post("/reset")
async def reset_state():
    """Reset the application state."""
    app_state["is_running"] = False
    app_state["current_city"] = None
    app_state["businesses"] = {}
    app_state["agent_updates"] = []
    app_state["session_id"] = None
    
    await manager.send_update({
        "type": "state_reset",
        "timestamp": datetime.now().isoformat(),
    })
    
    return RedirectResponse("/", status_code=303)

@app.post("/trigger_lead_manager")
async def trigger_lead_manager():
    """Trigger the Lead Manager agent manually."""
    logger.info("Manual trigger for Lead Manager agent requested")
    
    try:
        # Get or create session ID
        session_id = app_state.get("session_id")
        if not session_id:
            session_id = str(uuid.uuid4())
            app_state["session_id"] = session_id
        
        # Send initial update
        await manager.send_update({
            "type": "agent_status",
            "agent": "lead_manager",
            "status": "active",
            "message": "Lead Manager agent triggered manually",
            "timestamp": datetime.now().isoformat(),
        })
        
        # Call Lead Manager agent
        result = await call_lead_manager_agent("check_lead_emails", session_id)
        
        if result["success"]:
            logger.info(f"Lead Manager agent triggered successfully: {result['message']}")
            
            # Send success update
            await manager.send_update({
                "type": "agent_status", 
                "agent": "lead_manager",
                "status": "idle",
                "message": result["message"] or "Lead management completed successfully",
                "timestamp": datetime.now().isoformat(),
            })
            
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": result["message"] or "Lead Manager agent triggered successfully",
                    "timestamp": datetime.now().isoformat()
                }
            )
        else:
            logger.debug(f"Lead Manager agent failed: {result['error']}")
            
            # Send error update
            await manager.send_update({
                "type": "agent_status",
                "agent": "lead_manager", 
                "status": "error",
                "message": f"Error: {result['error']}",
                "timestamp": datetime.now().isoformat(),
            })
            
            return JSONResponse(
                status_code=500,
                content={"error": result["error"]}
            )
            
    except Exception as e:
        logger.error(f"Error triggering Lead Manager agent: {e}", exc_info=True)
        
        # Send error update
        await manager.send_update({
            "type": "agent_status",
            "agent": "lead_manager",
            "status": "error", 
            "message": f"Error triggering agent: {e}",
            "timestamp": datetime.now().isoformat(),
        })
        
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to trigger Lead Manager: {e}"}
        )

@app.post("/api/human-input")
async def receive_human_input_request(request: HumanInputRequest):
    """Receive a human input request from agents."""
    logger.info(f"Received human input request: {request.request_id} - {request.type}")
    
    # Store the request
    app_state["human_input_requests"][request.request_id] = request
    
    # Send notification to all connected WebSocket clients
    await manager.send_update({
        "type": "human_input_request",
        "request_id": request.request_id,
        "prompt": request.prompt,
        "input_type": request.type,
        "timestamp": request.timestamp,
    })
    
    return {
        "status": "received",
        "request_id": request.request_id,
        "message": "Human input request received. Please check the UI for the modal dialog.",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/human-input")
async def get_pending_human_input_requests():
    """Get all pending human input requests."""
    return {
        "requests": [req.dict() for req in app_state["human_input_requests"].values()],
        "count": len(app_state["human_input_requests"])
    }

@app.post("/api/human-input/{request_id}")
async def submit_human_input_response(request_id: str, response: HumanInputResponse):
    """Submit a response to a human input request."""
    if request_id not in app_state["human_input_requests"]:
        return JSONResponse(
            status_code=404,
            content={"error": "Request not found"}
        )
    
    # Get the request first (but don't remove it yet)
    original_request = app_state["human_input_requests"].get(request_id)
    
    logger.info(f"Human input response submitted for {request_id}: {response.response}")
    
    # Try to notify the human creation tool via HTTP callback to SDR agent
    success = False
    agent_url = os.environ.get("SDR_SERVICE_URL", config.DEFAULT_SDR_URL).rstrip("/")
    callback_url = f"{agent_url}/api/human-input/{request_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            agent_resp = await client.post(
                callback_url,
                json={"url": response.response},
                headers={"Content-Type": "application/json"}
            )
            if agent_resp.status_code == 200:
                logger.info(f"Successfully notified human creation tool on agent for request {request_id}")
                success = True
            else:
                logger.warning(f"Agent returned status {agent_resp.status_code} for request {request_id}: {agent_resp.text}")
    except httpx.ConnectError:
        logger.warning(f"Connection to SDR agent failed for request {request_id}")
    except Exception as e:
        logger.error(f"Error notifying SDR agent for request {request_id}: {e}")
    
    # Only remove the request from UI state AFTER successful processing
    if success:
        app_state["human_input_requests"].pop(request_id, None)
    
    # Send WebSocket notification that response was submitted
    await manager.send_update({
        "type": "human_input_response_submitted",
        "request_id": request_id,
        "response": response.response,
        "timestamp": datetime.now().isoformat()
    })
    
    return {
        "status": "success",
        "request_id": request_id,
        "message": "Response submitted successfully",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint for Railway and load balancers.
    Returns 200 OK when the service is healthy.
    """
    # Check if Firebase is available
    firebase_status = "unavailable"
    if BIGQUERY_AVAILABLE:
        try:
            from .firebase_service import get_firebase_service
            fb = get_firebase_service()
            firebase_status = "connected" if fb.is_available() else "not_configured"
        except:
            firebase_status = "error"
    
    return {
        "status": "healthy",
        "service": "leadpilot-ui",
        "version": "1.0.0",
        "environment": os.environ.get("RAILWAY_ENVIRONMENT", "local"),
        "timestamp": datetime.now().isoformat(),
        "components": {
            "websocket_connections": len(manager.active_connections),
            "business_count": len(app_state["businesses"]),
            "firebase": firebase_status,
            "email_tracker": "active" if EMAIL_TRACKER_AVAILABLE and email_tracker_instance else "unavailable",
            "auth": "enabled" if AUTH_AVAILABLE else "disabled",
        },
        "current_city": app_state["current_city"],
        "is_running": app_state["is_running"],
    }


@app.get("/")
async def root_health():
    """Root endpoint - redirects to dashboard or returns health for simple checks."""
    # For API health checks, return OK
    return RedirectResponse(url="/dashboard", status_code=302)

@app.post("/send_email")
async def send_email_endpoint(
    request: Request,
    business_id: str = Form(...),
    recipient_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...)
):
    """
    Send an email to a business lead with the generated proposal.
    Uses SMTP configuration from environment variables.
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    try:
        # Get SMTP configuration from environment
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        email_username = os.getenv("EMAIL_USERNAME")
        email_password = os.getenv("EMAIL_PASSWORD")
        from_email = os.getenv("FROM_EMAIL", email_username)
        
        if not email_username or not email_password:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Email not configured. Please set EMAIL_USERNAME and EMAIL_PASSWORD in .env"}
            )
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        logger.info(f"Sending email to {recipient_email} via SMTP...")
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_username, email_password)
            server.send_message(msg)
        
        logger.info(f"Email sent successfully to {recipient_email}")
        
        # Update business status if it exists
        if business_id in app_state["businesses"]:
            business = app_state["businesses"][business_id]
            business.notes.append(f"Email sent to {recipient_email} at {datetime.now().isoformat()}")
            
            # Send WebSocket update
            await manager.send_update({
                "type": "email_sent",
                "business_id": business_id,
                "business_name": business.name,
                "recipient": recipient_email,
                "message": f"Email sent to {recipient_email}",
                "timestamp": datetime.now().isoformat(),
            })
            
            # Persist email event to Firebase (email sent is part of SDR engagement)
            if BIGQUERY_AVAILABLE:
                try:
                    user_info = {}
                    if AUTH_AVAILABLE:
                        try:
                            user = await get_current_user(request)
                            user_info = {
                                "user_id": user.get("sub", "anonymous") if user else "anonymous",
                                "email": user.get("email") if user else None,
                                "name": user.get("name") if user else None,
                            }
                        except Exception as auth_err:
                            logger.warning(f"Could not get user for Firebase: {auth_err}")
                    
                    # Get research data if available
                    research_data = None
                    if "sdr_results" in app_state and business_id in app_state["sdr_results"]:
                        research_data = app_state["sdr_results"][business_id].get("research")
                    
                    bq_result = await persist_sdr_engaged(
                        lead_id=business_id,
                        user_info=user_info,
                        lead_details=business.model_dump(),
                        research_data=research_data,
                    )
                    
                    if bq_result.get("success"):
                        logger.info(f"✅ Email event for {business.name} persisted to Firebase")
                    elif not bq_result.get("skipped"):
                        logger.error(f"❌ Firebase email event failed: {bq_result.get('error')}")
                except Exception as bq_error:
                    logger.error(f"❌ Firebase persistence exception: {bq_error}", exc_info=True)
            else:
                logger.info("⏭️ Firebase not available, email event not persisted")
        
        return JSONResponse(
            status_code=200,
            content={"success": True, "message": f"Email sent successfully to {recipient_email}"}
        )
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication failed: {e}")
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Email authentication failed. Check EMAIL_USERNAME and EMAIL_PASSWORD."}
        )
    except Exception as e:
        logger.error(f"Failed to send email: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Failed to send email: {str(e)}"}
        )


@app.post("/send_confirmation_email")
async def send_confirmation_email(
    request: Request,
    business_id: str = Form(...),
    email_body: str = Form(...)
):
    """
    Send personalized email with confirmation button to kundarvinayak2004@gmail.com.
    Updates business status to 'pending' until confirmed.
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    try:
        # Check if business exists
        if business_id not in app_state["businesses"]:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Business not found"}
            )
        
        business = app_state["businesses"][business_id]
        
        # Get SMTP configuration
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        email_username = os.getenv("EMAIL_USERNAME")
        email_password = os.getenv("EMAIL_PASSWORD")
        from_email = os.getenv("FROM_EMAIL", email_username)
        recipient_email = "kundarvinayak2004@gmail.com"
        
        if not email_username or not email_password:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Email not configured"}
            )
        
        # Generate a simple confirmation code for easy reference
        import hashlib
        confirmation_code = hashlib.md5(f"{business_id}-confirm".encode()).hexdigest()[:8].upper()
        
        # Create HTML email with confirmation instructions
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">New Lead Proposal - {business.name}</h2>
                <div style="white-space: pre-wrap; background: #f9f9f9; padding: 15px; border-radius: 5px; margin: 20px 0;">
{email_body}
                </div>
                
                <div style="margin: 30px 0; text-align: center; background: #e8f5e9; padding: 25px; border-radius: 10px; border: 2px solid #28a745;">
                    <h3 style="color: #28a745; margin-top: 0;">Interested in this opportunity?</h3>
                    <p style="color: #333; margin-bottom: 15px;">
                        Simply <strong>reply to this email</strong> with "YES" or "INTERESTED" to confirm!
                    </p>
                    <div style="background: #fff; padding: 15px; border-radius: 5px; margin-top: 10px;">
                        <p style="margin: 0; color: #666; font-size: 12px;">Reference Code:</p>
                        <p style="margin: 5px 0 0 0; font-size: 24px; font-weight: bold; color: #28a745; letter-spacing: 2px;">
                            {confirmation_code}
                        </p>
                    </div>
                </div>
                
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 12px;">
                    <p><strong>Business Details:</strong></p>
                    <ul style="list-style: none; padding: 0;">
                        <li>📍 <strong>Location:</strong> {business.city or 'N/A'}</li>
                        <li>📞 <strong>Phone:</strong> {business.phone or 'N/A'}</li>
                        <li>⭐ <strong>Status:</strong> {business.status}</li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = from_email
        msg['To'] = recipient_email
        msg['Subject'] = f"Lead Proposal: {business.name} - Awaiting Your Response"
        
        # Attach both plain text and HTML versions
        plain_text = email_body + f"\n\n---\nInterested? Simply reply with 'YES' or 'INTERESTED' to confirm!\nReference Code: {confirmation_code}"
        text_part = MIMEText(plain_text, 'plain')
        html_part = MIMEText(html_body, 'html')
        msg.attach(text_part)
        msg.attach(html_part)
        
        # Send email
        logger.info(f"Sending confirmation email for {business.name} to {recipient_email}")
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_username, email_password)
            server.send_message(msg)
        
        logger.info(f"Confirmation email sent successfully")
        
        # Register with email tracker for automatic confirmation
        if EMAIL_TRACKER_AVAILABLE and email_tracker_instance:
            # Extract user info to pass through to auto-confirm callback
            _tracker_user_info = {}
            if AUTH_AVAILABLE:
                try:
                    _u = await get_current_user(request)
                    _tracker_user_info = {
                        "user_id": _u.get("sub", "anonymous") if _u else "anonymous",
                        "email": _u.get("email") if _u else None,
                        "name": _u.get("name") if _u else None,
                    }
                except Exception:
                    pass
            email_tracker_instance.register_pending_lead(
                business_id=business_id,
                business_name=business.name,
                business_data=business.model_dump(),
                user_info=_tracker_user_info
            )
            logger.info(f"📧 Lead registered for email reply tracking: {business.name}")
        
        # Update business status to pending
        business.status = "pending"
        business.notes.append(f"Confirmation email sent at {datetime.now().isoformat()}")
        business.notes.append(f"Email tracking enabled - auto-confirm on positive reply")
        
        # Send WebSocket update
        await manager.send_update({
            "type": "business_updated",
            "agent": "sdr",
            "business": business.model_dump(),
            "update": {
                "status": "pending",
                "message": "Confirmation email sent, awaiting response"
            },
            "timestamp": datetime.now().isoformat(),
        })
        
        # Persist to Firebase — confirmation email sent is part of SDR engagement
        if BIGQUERY_AVAILABLE:
            try:
                user_info = {}
                if AUTH_AVAILABLE:
                    try:
                        user = await get_current_user(request)
                        user_info = {
                            "user_id": user.get("sub", "anonymous") if user else "anonymous",
                            "email": user.get("email") if user else None,
                            "name": user.get("name") if user else None,
                        }
                    except Exception:
                        pass
                research_data = None
                if "sdr_results" in app_state and business_id in app_state["sdr_results"]:
                    research_data = app_state["sdr_results"][business_id].get("research")
                bq_result = await persist_sdr_engaged(
                    lead_id=business_id,
                    user_info=user_info,
                    lead_details=business.model_dump(),
                    research_data=research_data,
                )
                if bq_result.get("success"):
                    logger.info(f"✅ Confirmation email for {business.name} persisted to Firebase")
                elif not bq_result.get("skipped"):
                    logger.error(f"❌ Firebase persist failed for confirmation email: {bq_result.get('error')}")
            except Exception as bq_err:
                logger.error(f"❌ Firebase persist exception: {bq_err}")
        
        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Confirmation email sent successfully"}
        )
        
    except Exception as e:
        logger.error(f"Failed to send confirmation email: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Failed to send email: {str(e)}"}
        )


@app.api_route("/confirm_lead/{business_id}", methods=["GET", "POST"])
async def confirm_lead(business_id: str, request: Request):
    """
    Handles lead confirmation - either from email link (GET) or dashboard button (POST).
    Moves lead from SDR column to Lead Manager column.
    """
    try:
        if business_id not in app_state["businesses"]:
            if request.method == "POST":
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": "Lead not found"}
                )
            return HTMLResponse(
                content="<h1>Error: Lead not found</h1><p>This confirmation link may be invalid or expired.</p>",
                status_code=404
            )
        
        business = app_state["businesses"][business_id]
        
        # Update business status to confirmed and move to lead_manager column
        business.status = "confirmed"
        business.notes.append(f"Lead confirmed at {datetime.now().isoformat()}")
        
        logger.info(f"Lead {business.name} confirmed, moving to Lead Manager")
        
        # Send WebSocket update to move business to Lead Manager column
        await manager.send_update({
            "type": "lead_confirmed",
            "agent": "lead_manager",
            "business": business.model_dump(),
            "update": {
                "status": "confirmed",
                "message": "Lead confirmed and moved to Lead Manager"
            },
            "timestamp": datetime.now().isoformat(),
        })
        
        # NOTE: Dashboard confirm only moves lead to Lead Manager column in UI
        # It should NOT change the Firebase status (SDR_ENGAGED, CONVERTING, MEETING_SCHEDULED)
        # The Firebase status reflects WHERE the lead came from (what action was taken)
        # Only adding a note to Firebase to track this UI action
        if BIGQUERY_AVAILABLE:
            try:
                note = f"Lead moved to Lead Manager column at {datetime.now().isoformat()}"
                await add_note_to_lead(business_id, note)
                logger.info(f"✅ Added note to Firebase for lead {business.name} (status preserved)")
            except Exception as note_error:
                logger.warning(f"Could not add note to Firebase: {note_error}")
        
        # For POST requests (from dashboard), return JSON
        if request.method == "POST":
            return JSONResponse(content={"success": True, "message": f"Lead {business.name} confirmed"})
        
        # For GET requests (from email link), return HTML page
        success_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Lead Confirmed</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    text-align: center;
                    max-width: 500px;
                }}
                .success-icon {{
                    font-size: 60px;
                    color: #28a745;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #2c3e50;
                    margin-bottom: 10px;
                }}
                p {{
                    color: #666;
                    line-height: 1.6;
                }}
                .business-name {{
                    color: #667eea;
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-icon">✓</div>
                <h1>Lead Confirmed Successfully!</h1>
                <p>Thank you for confirming your interest in <span class="business-name">{business.name}</span>.</p>
                <p>This lead has been moved to the Lead Manager and our team will follow up shortly.</p>
                <p style="margin-top: 30px; color: #999; font-size: 14px;">You can close this window now.</p>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=success_html)
        
    except Exception as e:
        logger.error(f"Error confirming lead: {e}", exc_info=True)
        return HTMLResponse(
            content=f"<h1>Error</h1><p>Failed to confirm lead: {str(e)}</p>",
            status_code=500
        )


@app.get("/debug/static")
async def debug_static():
    """Debug endpoint to check static file configuration."""
    import os
    
    static_files_info = {
        "static_dir": str(static_dir),
        "static_dir_exists": static_dir.exists(),
        "templates_dir": str(templates_dir),
        "templates_dir_exists": templates_dir.exists(),
        "working_directory": os.getcwd(),
        "module_file_location": str(Path(__file__)),
        "module_dir": str(module_dir)
    }
    
    # List static files if directory exists
    if static_dir.exists():
        try:
            static_files = []
            for root, dirs, files in os.walk(static_dir):
                for file in files:
                    rel_path = os.path.relpath(os.path.join(root, file), static_dir)
                    static_files.append(rel_path)
            static_files_info["static_files"] = static_files
        except Exception as e:
            static_files_info["static_files_error"] = str(e)
    else:
        static_files_info["static_files"] = "Directory does not exist"
    
    return static_files_info


# ===== Meeting Scheduling Endpoints =====

@app.post("/schedule_meeting")
async def schedule_meeting(request: ScheduleMeetingRequest, req: Request):
    """
    Schedule a meeting with a lead using Google Calendar.
    Creates a real Google Calendar event with Google Meet link.
    Moves the lead from Lead Manager to Calendar column.
    """
    logger.info(f"Scheduling meeting for business: {request.business_id}")
    
    # Get the business
    business = app_state["businesses"].get(request.business_id)
    if not business:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Business not found"}
        )
    
    # Check if calendar utilities are available
    if not CALENDAR_UTILS_AVAILABLE:
        logger.warning("Calendar utilities not available, using fallback method")
        
        # Even without calendar utils, update status to MEETING_SCHEDULED in Firebase
        business.status = BusinessStatus.MEETING_SCHEDULED
        business.updated_at = datetime.now()
        business.notes.append(f"Meeting scheduled (manual): {request.title} on {request.date} at {request.time}")
        
        # Persist to Firebase
        if BIGQUERY_AVAILABLE:
            try:
                user_info = {}
                if AUTH_AVAILABLE:
                    try:
                        user = await get_current_user(req)
                        user_info = {
                            "user_id": user.get("sub", "anonymous") if user else "anonymous",
                            "email": user.get("email") if user else None,
                            "name": user.get("name") if user else None,
                        }
                    except Exception:
                        pass
                
                meeting_data = {
                    "title": request.title,
                    "date": request.date,
                    "time": request.time,
                    "duration": request.duration,
                    "attendee": request.attendee_email,
                }
                
                bq_result = await persist_meeting_scheduled(
                    lead_id=request.business_id,
                    user_info=user_info,
                    lead_details=business.model_dump(),
                    meeting_details=meeting_data,
                )
                if bq_result.get("success"):
                    logger.info(f"✅ Meeting (manual) for {business.name} persisted to Firebase (MEETING_SCHEDULED)")
                else:
                    logger.error(f"❌ Firebase persistence failed for manual meeting: {bq_result.get('error')}")
            except Exception as e:
                logger.error(f"❌ Firebase persistence exception: {e}")
        
        # Send WebSocket update to move card to Calendar column
        await manager.send_update({
            "type": "business_updated",
            "agent": "calendar",
            "business": business.model_dump(),
            "update": {
                "status": "meeting_scheduled",
                "message": f"Meeting scheduled (manual): {request.title}",
            },
            "timestamp": datetime.now().isoformat(),
        })
        
        # Fallback: return info for manual calendar creation
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "fallback": True,
                "message": "Calendar API not available. Please create meeting manually.",
                "meeting_info": {
                    "title": request.title,
                    "date": request.date,
                    "time": request.time,
                    "duration": request.duration,
                    "attendee": request.attendee_email,
                    "description": request.description
                }
            }
        )
    
    try:
        # Create the meeting using calendar utilities
        meeting_result = await create_meeting_with_lead(
            lead_name=business.name,
            lead_email=request.attendee_email or business.email or "",
            meeting_subject=request.title,
            description=request.description or f"Meeting with {business.name} - Scheduled via LeadPilot",
            duration_minutes=request.duration,
            preferred_date=request.date,
            preferred_time=request.time
        )
        
        if not meeting_result.get("success"):
            logger.error(f"Failed to create meeting: {meeting_result.get('error')}")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": meeting_result.get("error", "Failed to create meeting"),
                    "message": meeting_result.get("message", "Unknown error occurred")
                }
            )
        
        # Meeting created successfully
        meet_link = meeting_result.get("meet_link", "")
        calendar_link = meeting_result.get("calendar_link", "")
        
        logger.info(f"Meeting created successfully: {meeting_result.get('meeting_id')}")
        logger.info(f"Meet link: {meet_link}")
        
        # Update business status to meeting_scheduled
        business.status = BusinessStatus.MEETING_SCHEDULED
        business.updated_at = datetime.now()
        business.notes.append(f"Meeting scheduled: {request.title} on {request.date} at {request.time}")
        if meet_link:
            business.notes.append(f"Google Meet: {meet_link}")
        
        # Prepare meeting data for WebSocket
        meeting_data = {
            "meeting_id": meeting_result.get("meeting_id"),
            "title": request.title,
            "date": request.date,
            "time": request.time,
            "duration": request.duration,
            "meet_link": meet_link,
            "calendar_link": calendar_link,
            "attendee": request.attendee_email or business.email,
            "start_datetime": f"{request.date}T{request.time}:00",
            "end_datetime": meeting_result.get("end_time"),
            "description": request.description
        }
        
        # Send business update via WebSocket (moves card to Calendar column)
        await manager.send_update({
            "type": "business_updated",
            "agent": "calendar",
            "business": business.model_dump(),
            "update": {
                "status": "meeting_scheduled",
                "message": f"Meeting scheduled: {request.title}",
                "meeting_data": meeting_data
            },
            "timestamp": datetime.now().isoformat(),
        })
        
        # Send calendar notification with meeting details
        await manager.send_update({
            "type": "meeting_scheduled",
            "agent": "calendar",
            "business_id": request.business_id,
            "business_name": business.name,
            "meeting": meeting_data,
            "timestamp": datetime.now().isoformat(),
        })
        
        # Persist to Firebase if available - this is a CONFIRMED meeting
        if BIGQUERY_AVAILABLE:
            try:
                user_info = {}
                try:
                    if AUTH_AVAILABLE:
                        user = await get_current_user(req)
                        user_info = {
                            "user_id": user.get("sub", "anonymous") if user else "anonymous",
                            "email": user.get("email") if user else None,
                            "name": user.get("name") if user else None,
                        }
                except Exception as auth_err:
                    logger.warning(f"Could not get user info for Firebase: {auth_err}")
                
                # Call with correct parameters - must await async function
                bq_result = await persist_meeting_scheduled(
                    lead_id=request.business_id,
                    user_info=user_info,
                    lead_details=business.model_dump(),
                    meeting_details=meeting_data,
                )
                
                if bq_result.get("success"):
                    logger.info(f"✅ Meeting for {business.name} persisted to Firebase (MEETING_SCHEDULED)")
                else:
                    logger.error(f"❌ Firebase persistence FAILED for meeting: {bq_result.get('error')}")
            except Exception as e:
                logger.error(f"❌ Firebase persistence exception: {e}", exc_info=True)
        else:
            logger.info("⏭️ Firebase not available, meeting not persisted")
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": f"Meeting scheduled successfully with {business.name}",
                "meeting": meeting_data
            }
        )
        
    except Exception as e:
        logger.error(f"Error scheduling meeting: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "message": f"Failed to schedule meeting: {str(e)}"
            }
        )


# ===== Email Tracking Endpoints =====

@app.get("/email_tracking/status")
async def get_email_tracking_status():
    """Get the current status of email reply tracking."""
    if not EMAIL_TRACKER_AVAILABLE or not email_tracker_instance:
        return JSONResponse(content={
            "enabled": False,
            "message": "Email tracking is not available"
        })
    
    pending_leads = email_tracker_instance.get_pending_leads()
    
    return JSONResponse(content={
        "enabled": True,
        "is_running": email_tracker_instance.is_running,
        "check_interval": email_tracker_instance.check_interval,
        "pending_leads_count": len(pending_leads),
        "pending_leads": [
            {
                "reference_code": code,
                "business_name": info.get("business_name"),
                "sent_at": info.get("sent_at"),
                "status": info.get("status")
            }
            for code, info in pending_leads.items()
        ]
    })


@app.post("/email_tracking/check_now")
async def force_email_check():
    """Force an immediate check for email replies."""
    if not EMAIL_TRACKER_AVAILABLE or not email_tracker_instance:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Email tracking is not available"}
        )
    
    try:
        # Run the check in background
        asyncio.create_task(email_tracker_instance._check_for_replies())
        
        return JSONResponse(content={
            "success": True,
            "message": "Email check initiated. Results will appear automatically via WebSocket."
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


if __name__ == "__main__":
    import uvicorn
    
    logger.info("--- Starting FastAPI server for UI Client ---")
    logger.info("Ensure dependent A2A services are running:")
    logger.info(f"  Lead Finder: python -m lead_finder --port {config.DEFAULT_LEAD_FINDER_PORT}")
    logger.info(f"  SDR: python -m sdr --port {config.DEFAULT_SDR_PORT}")
    logger.info(f"  Lead Manager: python -m lead_manager --port {config.DEFAULT_LEAD_MANAGER_PORT}")
    logger.info(f"--- Access UI at http://0.0.0.0:{config.UI_CLIENT_SERVICE_NAME} ---")
    
    uvicorn.run(
        "ui_client.main:app",
        host="0.0.0.0",
        port=config.UI_CLIENT_SERVICE_NAME,
        reload=True
    )