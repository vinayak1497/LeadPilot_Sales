"""
BigQuery Persistence Service for LeadPilot.

Persists confirmed lead data to BigQuery with user context, 
status tracking, and meeting details.

SCHEMA (24 fields - must match exactly):
- lead_id (STRING, REQUIRED)
- user_id (STRING, NULLABLE)
- user_email (STRING, NULLABLE)
- user_name (STRING, NULLABLE)
- status (STRING, REQUIRED)
- business_name (STRING, REQUIRED)
- business_phone (STRING, NULLABLE)
- business_email (STRING, NULLABLE)
- business_address (STRING, NULLABLE)
- business_city (STRING, NULLABLE)
- business_category (STRING, NULLABLE)
- business_rating (FLOAT, NULLABLE)
- research_summary (STRING, NULLABLE)
- research_industry (STRING, NULLABLE)
- research_priority (STRING, NULLABLE)
- meeting_date (STRING, NULLABLE)
- meeting_time (STRING, NULLABLE)
- meeting_calendar_link (STRING, NULLABLE)
- email_sent (BOOLEAN, NULLABLE)
- email_sent_at (TIMESTAMP, NULLABLE)
- email_subject (STRING, NULLABLE)
- created_at (TIMESTAMP, REQUIRED)
- updated_at (TIMESTAMP, REQUIRED)
- status_changed_at (TIMESTAMP, NULLABLE)
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)

# BigQuery Configuration from environment
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "leadpilot-gdg")
DATASET_ID = os.environ.get("DATASET_ID", "leadpilot_dataset")
TABLE_ID = os.environ.get("TABLE_ID", "business_leads")
CREDENTIALS_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")

# Authoritative schema - fields that exist in the actual BigQuery table
# Any field NOT in this set will be stripped before insert
VALID_SCHEMA_FIELDS: Set[str] = {
    "lead_id", "user_id", "user_email", "user_name", "status",
    "business_name", "business_phone", "business_email", "business_address",
    "business_city", "business_category", "business_rating",
    "research_summary", "research_industry", "research_priority",
    "meeting_date", "meeting_time", "meeting_calendar_link",
    "email_sent", "email_sent_at", "email_subject",
    "created_at", "updated_at", "status_changed_at",
}

# Required fields that must have values (non-null)
REQUIRED_FIELDS: Set[str] = {
    "lead_id", "status", "business_name", "created_at", "updated_at"
}

# Try to import BigQuery
try:
    from google.cloud import bigquery
    from google.cloud.exceptions import NotFound, Conflict
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False
    logger.warning("google-cloud-bigquery not installed. BigQuery persistence disabled.")


class LeadStatus(str, Enum):
    """Lead lifecycle statuses for BigQuery tracking."""
    ENGAGED_SDR = "ENGAGED_SDR"
    CONVERTING = "CONVERTING"
    MEETING_SCHEDULED = "MEETING_SCHEDULED"


class BigQueryLeadService:
    """
    Service for persisting lead data to BigQuery.
    
    Handles:
    - Lead status updates (SDR engaged, converting, meeting scheduled)
    - User context tracking
    - Meeting details persistence
    - Graceful error handling
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern to reuse BigQuery client."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.client = None
        self.dataset_ref = None
        self.table_ref = None
        self._initialized = True
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the BigQuery client with service account credentials."""
        if not BIGQUERY_AVAILABLE:
            logger.warning("⚠️ BigQuery library not available. Persistence disabled.")
            return
        
        if not PROJECT_ID:
            logger.warning("⚠️ GOOGLE_CLOUD_PROJECT not set. BigQuery persistence disabled.")
            return
        
        try:
            # Initialize client with project
            self.client = bigquery.Client(project=PROJECT_ID)
            self.dataset_ref = self.client.dataset(DATASET_ID)
            self.table_ref = self.dataset_ref.table(TABLE_ID)
            
            # Log full table path for verification
            full_table_path = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
            logger.info(f"🔗 BigQuery client initialized")
            logger.info(f"   Project: {PROJECT_ID}")
            logger.info(f"   Dataset: {DATASET_ID}")
            logger.info(f"   Table: {TABLE_ID}")
            logger.info(f"   Full path: {full_table_path}")
            
            # Ensure dataset and table exist
            self._ensure_infrastructure()
            
            # Verify table is accessible
            try:
                table = self.client.get_table(self.table_ref)
                logger.info(f"✅ Table verified: {table.num_rows} existing rows, {len(table.schema)} schema fields")
            except Exception as table_err:
                logger.warning(f"⚠️ Could not verify table: {table_err}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize BigQuery client: {e}")
            self.client = None
    
    def _ensure_infrastructure(self):
        """Ensure dataset and table exist with proper schema."""
        if not self.client:
            return
        
        # Ensure dataset exists
        try:
            self.client.get_dataset(self.dataset_ref)
            logger.info(f"Dataset {DATASET_ID} exists")
        except NotFound:
            logger.info(f"Creating dataset {DATASET_ID}")
            dataset = bigquery.Dataset(self.dataset_ref)
            dataset.description = "LeadPilot confirmed leads tracking"
            dataset.location = "US"
            self.client.create_dataset(dataset)
            logger.info(f"Dataset {DATASET_ID} created")
        
        # Ensure table exists with proper schema
        try:
            self.client.get_table(self.table_ref)
            logger.info(f"Table {TABLE_ID} exists")
        except NotFound:
            self._create_leads_table()
    
    def _create_leads_table(self):
        """Create the leads table with the proper schema matching actual table."""
        if not self.client:
            return
        
        logger.info(f"Creating table {TABLE_ID}")
        
        # Schema MUST match actual BigQuery table - 24 fields exactly
        schema = [
            # Lead Identification
            bigquery.SchemaField("lead_id", "STRING", mode="REQUIRED", 
                                 description="Unique lead identifier"),
            
            # User Information
            bigquery.SchemaField("user_id", "STRING", mode="NULLABLE",
                                 description="Authenticated user ID"),
            bigquery.SchemaField("user_email", "STRING", mode="NULLABLE",
                                 description="User email address"),
            bigquery.SchemaField("user_name", "STRING", mode="NULLABLE",
                                 description="User display name"),
            
            # Lead Status
            bigquery.SchemaField("status", "STRING", mode="REQUIRED",
                                 description="Lead status: ENGAGED_SDR, CONVERTING, MEETING_SCHEDULED"),
            
            # Business Information
            bigquery.SchemaField("business_name", "STRING", mode="REQUIRED",
                                 description="Business name"),
            bigquery.SchemaField("business_phone", "STRING", mode="NULLABLE",
                                 description="Business phone number"),
            bigquery.SchemaField("business_email", "STRING", mode="NULLABLE",
                                 description="Business email address"),
            bigquery.SchemaField("business_address", "STRING", mode="NULLABLE",
                                 description="Business address"),
            bigquery.SchemaField("business_city", "STRING", mode="NULLABLE",
                                 description="Business city"),
            bigquery.SchemaField("business_category", "STRING", mode="NULLABLE",
                                 description="Business category/industry"),
            bigquery.SchemaField("business_rating", "FLOAT", mode="NULLABLE",
                                 description="Business rating (1-5)"),
            
            # Research Data
            bigquery.SchemaField("research_summary", "STRING", mode="NULLABLE",
                                 description="AI research summary"),
            bigquery.SchemaField("research_industry", "STRING", mode="NULLABLE",
                                 description="Identified industry"),
            bigquery.SchemaField("research_priority", "STRING", mode="NULLABLE",
                                 description="Lead priority: high, medium, low"),
            
            # Meeting Details - STRING type to match actual table
            bigquery.SchemaField("meeting_date", "STRING", mode="NULLABLE",
                                 description="Scheduled meeting date (stored as string)"),
            bigquery.SchemaField("meeting_time", "STRING", mode="NULLABLE",
                                 description="Scheduled meeting time (stored as string)"),
            bigquery.SchemaField("meeting_calendar_link", "STRING", mode="NULLABLE",
                                 description="Calendar event link"),
            
            # Email Tracking
            bigquery.SchemaField("email_sent", "BOOLEAN", mode="NULLABLE",
                                 description="Whether email was sent"),
            bigquery.SchemaField("email_sent_at", "TIMESTAMP", mode="NULLABLE",
                                 description="When email was sent"),
            bigquery.SchemaField("email_subject", "STRING", mode="NULLABLE",
                                 description="Email subject line"),
            
            # Timestamps
            bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED",
                                 description="Record creation timestamp"),
            bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED",
                                 description="Last update timestamp"),
            bigquery.SchemaField("status_changed_at", "TIMESTAMP", mode="NULLABLE",
                                 description="When status was last changed"),
        ]
        
        table = bigquery.Table(self.table_ref, schema=schema)
        table.description = "LeadPilot confirmed leads with user tracking"
        
        # Add partitioning for better query performance
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="created_at"
        )
        table.clustering_fields = ["user_id", "status", "business_city"]
        
        self.client.create_table(table)
        logger.info(f"Table {TABLE_ID} created successfully")
    
    def _validate_and_clean_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate row against schema and remove any fields not in schema.
        This ensures we NEVER try to insert fields that don't exist in the table.
        """
        # Strip any fields not in the valid schema
        cleaned = {}
        stripped_fields = []
        
        for key, value in row.items():
            if key in VALID_SCHEMA_FIELDS:
                cleaned[key] = value
            else:
                stripped_fields.append(key)
        
        if stripped_fields:
            logger.warning(f"⚠️ Stripped non-schema fields: {stripped_fields}")
        
        return cleaned
    
    def _validate_required_fields(self, row: Dict[str, Any]) -> Optional[str]:
        """
        Check that all required fields are present and non-null.
        Returns error message if validation fails, None if valid.
        """
        missing = []
        for field in REQUIRED_FIELDS:
            if field not in row or row[field] is None:
                missing.append(field)
        
        if missing:
            return f"Missing required fields: {missing}"
        return None

    async def persist_lead_status(
        self,
        lead_id: str,
        status: LeadStatus,
        user_info: Dict[str, Any],
        lead_details: Dict[str, Any],
        meeting_details: Optional[Dict[str, Any]] = None,
        email_details: Optional[Dict[str, Any]] = None,
        research_data: Optional[Dict[str, Any]] = None,
        previous_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Persist a lead status update to BigQuery.
        
        CRITICAL: This method strictly validates against the actual table schema.
        Any fields not in VALID_SCHEMA_FIELDS will be stripped before insert.
        
        Args:
            lead_id: Unique identifier for the lead
            status: Current lead status
            user_info: Dict with user_id, email, name
            lead_details: Business information dict
            meeting_details: Optional meeting info (date, time, link)
            email_details: Optional email tracking info
            research_data: Optional AI research data
            previous_status: Previous status if known (ignored - not in schema)
            
        Returns:
            Dict with success status and any error message
        """
        # Pre-flight check: is BigQuery available?
        if not self.client:
            logger.warning("⏭️ BigQuery client not available - skipping persistence for lead %s", lead_id)
            return {"success": False, "error": "BigQuery not configured", "skipped": True}
        
        # Validate lead_id
        if not lead_id or not str(lead_id).strip():
            logger.error("❌ Cannot persist: lead_id is empty or None")
            return {"success": False, "error": "lead_id is required"}
        
        try:
            now = datetime.utcnow()
            now_iso = now.isoformat() + "Z"
            
            logger.info(f"📝 Preparing BigQuery insert for lead: {lead_id}, status: {status.value}")
            logger.info(f"   Target: {PROJECT_ID}.{DATASET_ID}.{TABLE_ID}")
            
            # Build the row data - STRICTLY aligned with actual table schema (24 fields)
            row = {
                # Required fields
                "lead_id": str(lead_id).strip(),
                "status": status.value,
                "business_name": str(lead_details.get("name", "Unknown")).strip() or "Unknown",
                "created_at": now_iso,
                "updated_at": now_iso,
                
                # User info (nullable)
                "user_id": str(user_info.get("user_id")).strip() if user_info.get("user_id") else None,
                "user_email": user_info.get("email"),
                "user_name": user_info.get("name"),
                
                # Business info (nullable)
                "business_phone": lead_details.get("phone"),
                "business_email": lead_details.get("email"),
                "business_address": lead_details.get("address"),
                "business_city": lead_details.get("city"),
                "business_category": lead_details.get("category"),
                "business_rating": None,
                
                # Research data (nullable)
                "research_summary": None,
                "research_industry": None,
                "research_priority": None,
                
                # Meeting details (nullable) - stored as STRING
                "meeting_date": None,
                "meeting_time": None,
                "meeting_calendar_link": None,
                
                # Email tracking (nullable)
                "email_sent": None,
                "email_sent_at": None,
                "email_subject": None,
                
                # Status changed (nullable)
                "status_changed_at": now_iso,
            }
            
            # Handle business_rating carefully (must be FLOAT)
            rating = lead_details.get("rating")
            if rating is not None:
                try:
                    row["business_rating"] = float(rating)
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ Invalid rating value: {rating}, setting to None")
                    row["business_rating"] = None
            
            # Add research data if available
            if research_data:
                overview = research_data.get("overview")
                if overview:
                    row["research_summary"] = str(overview)[:5000]
                row["research_industry"] = research_data.get("industry")
                # Safely extract priority from nested structure
                recommendation = research_data.get("recommendation")
                if isinstance(recommendation, dict):
                    row["research_priority"] = recommendation.get("priority")
            
            # Add email details if available
            if email_details:
                row["email_sent"] = True
                sent_at = email_details.get("sent_at")
                if sent_at:
                    sent_at_str = str(sent_at)
                    row["email_sent_at"] = sent_at_str if "Z" in sent_at_str else sent_at_str + "Z"
                else:
                    row["email_sent_at"] = now_iso
                row["email_subject"] = email_details.get("subject")
            
            # Add meeting details if status is MEETING_SCHEDULED
            if status == LeadStatus.MEETING_SCHEDULED and meeting_details:
                # meeting_date and meeting_time are STRING type
                if meeting_details.get("date"):
                    row["meeting_date"] = str(meeting_details["date"])
                if meeting_details.get("time"):
                    row["meeting_time"] = str(meeting_details["time"])
                row["meeting_calendar_link"] = meeting_details.get("calendar_link")
            
            # CRITICAL: Validate and clean row against schema
            row_validated = self._validate_and_clean_row(row)
            
            # Remove None values (BigQuery handles missing fields as NULL)
            row_cleaned = {k: v for k, v in row_validated.items() if v is not None}
            
            # Validate required fields
            validation_error = self._validate_required_fields(row_cleaned)
            if validation_error:
                logger.error(f"❌ Validation failed for lead {lead_id}: {validation_error}")
                return {"success": False, "error": validation_error, "lead_id": lead_id}
            
            # Log exactly what we're inserting
            logger.info(f"📤 Inserting {len(row_cleaned)} fields: {sorted(row_cleaned.keys())}")
            
            # Generate unique row ID for deduplication
            row_id = f"{lead_id}_{status.value}_{int(now.timestamp())}"
            
            # Execute the insert
            errors = self.client.insert_rows_json(
                self.table_ref,
                [row_cleaned],
                row_ids=[row_id]
            )
            
            # CRITICAL: Explicitly check for row-level errors
            # insert_rows_json returns a list of errors (empty list = success)
            if errors:
                error_details = []
                for error in errors:
                    if isinstance(error, dict):
                        row_errors = error.get('errors', [])
                        for e in row_errors:
                            reason = e.get('reason', 'unknown')
                            message = e.get('message', 'no message')
                            location = e.get('location', '')
                            error_details.append(f"[{reason}] {message} (field: {location})")
                    else:
                        error_details.append(str(error))
                
                error_msg = "; ".join(error_details) if error_details else str(errors)
                logger.error(f"❌ BigQuery INSERT FAILED for lead {lead_id}")
                logger.error(f"   Error: {error_msg}")
                logger.error(f"   Row data: {row_cleaned}")
                return {
                    "success": False, 
                    "error": error_msg, 
                    "lead_id": lead_id,
                    "row_id": row_id
                }
            
            # SUCCESS - no errors returned
            logger.info(f"✅ BigQuery INSERT SUCCESS for lead {lead_id}")
            logger.info(f"   Status: {status.value}")
            logger.info(f"   Business: {row_cleaned.get('business_name')}")
            logger.info(f"   Row ID: {row_id}")
            
            return {
                "success": True, 
                "lead_id": lead_id, 
                "status": status.value,
                "row_id": row_id
            }
            
        except Exception as e:
            logger.error(f"❌ Exception persisting lead to BigQuery: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def get_leads_by_user(self, user_id: str, status: Optional[LeadStatus] = None) -> List[Dict[str, Any]]:
        """
        Query leads for a specific user.
        
        Args:
            user_id: The user's ID
            status: Optional status filter
            
        Returns:
            List of lead records
        """
        if not self.client:
            return []
        
        try:
            query = f"""
                SELECT *
                FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
                WHERE user_id = @user_id
                {"AND status = @status" if status else ""}
                ORDER BY updated_at DESC
                LIMIT 100
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
                ]
            )
            
            if status:
                job_config.query_parameters.append(
                    bigquery.ScalarQueryParameter("status", "STRING", status.value)
                )
            
            query_job = self.client.query(query, job_config=job_config)
            results = query_job.result()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Failed to query leads: {e}")
            return []
    
    def is_available(self) -> bool:
        """Check if BigQuery service is available."""
        return self.client is not None


# Singleton instance
_bq_service: Optional[BigQueryLeadService] = None


def get_bigquery_service() -> BigQueryLeadService:
    """Get the BigQuery service singleton."""
    global _bq_service
    if _bq_service is None:
        _bq_service = BigQueryLeadService()
    return _bq_service


# Helper functions for easy integration
async def persist_sdr_engaged(
    lead_id: str,
    user_info: Dict[str, Any],
    lead_details: Dict[str, Any],
    research_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Persist when SDR engages with a lead.
    
    This is the FIRST stage of the lead lifecycle.
    Should be called when a lead is first processed by SDR.
    """
    if not lead_id:
        logger.warning("⏭️ persist_sdr_engaged: No lead_id provided, skipping")
        return {"success": False, "error": "No lead_id provided", "skipped": True}
    
    logger.info(f"🔔 PERSIST EVENT: SDR_ENGAGED for lead {lead_id}")
    service = get_bigquery_service()
    
    if not service.is_available():
        logger.warning(f"⏭️ BigQuery not available, skipping persist for lead {lead_id}")
        return {"success": False, "error": "BigQuery not available", "skipped": True}
    
    result = await service.persist_lead_status(
        lead_id=lead_id,
        status=LeadStatus.ENGAGED_SDR,
        user_info=user_info or {},
        lead_details=lead_details or {},
        research_data=research_data,
    )
    
    if result.get("success"):
        logger.info(f"✅ SDR_ENGAGED persisted successfully for lead {lead_id}")
    else:
        logger.error(f"❌ SDR_ENGAGED persistence FAILED for lead {lead_id}: {result.get('error')}")
    
    return result


async def persist_lead_converting(
    lead_id: str,
    user_info: Dict[str, Any],
    lead_details: Dict[str, Any],
    email_details: Optional[Dict[str, Any]] = None,
    research_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Persist when a lead is CONFIRMED/CONVERTING.
    
    This is the SECOND stage - lead has been confirmed by user action.
    This is a CRITICAL event - data MUST be written to BigQuery.
    """
    if not lead_id:
        logger.warning("⏭️ persist_lead_converting: No lead_id provided, skipping")
        return {"success": False, "error": "No lead_id provided", "skipped": True}
    
    logger.info(f"🔔 PERSIST EVENT: CONVERTING (CONFIRMED) for lead {lead_id}")
    service = get_bigquery_service()
    
    if not service.is_available():
        logger.error(f"❌ BigQuery not available - CANNOT persist confirmed lead {lead_id}!")
        return {"success": False, "error": "BigQuery not available", "skipped": True}
    
    result = await service.persist_lead_status(
        lead_id=lead_id,
        status=LeadStatus.CONVERTING,
        user_info=user_info or {},
        lead_details=lead_details or {},
        email_details=email_details,
        research_data=research_data,
    )
    
    if result.get("success"):
        logger.info(f"✅ CONVERTING persisted successfully for lead {lead_id}")
    else:
        logger.error(f"❌ CONVERTING persistence FAILED for lead {lead_id}: {result.get('error')}")
    
    return result


async def persist_meeting_scheduled(
    lead_id: str,
    user_info: Dict[str, Any],
    lead_details: Dict[str, Any],
    meeting_details: Dict[str, Any],
    research_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Persist when a meeting is scheduled with a lead.
    
    This is the THIRD stage - a meeting has been scheduled.
    This is a CRITICAL event - data MUST be written to BigQuery.
    """
    if not lead_id:
        logger.warning("⏭️ persist_meeting_scheduled: No lead_id provided, skipping")
        return {"success": False, "error": "No lead_id provided", "skipped": True}
    
    logger.info(f"🔔 PERSIST EVENT: MEETING_SCHEDULED for lead {lead_id}")
    logger.info(f"   Meeting details: {meeting_details}")
    
    service = get_bigquery_service()
    
    if not service.is_available():
        logger.error(f"❌ BigQuery not available - CANNOT persist meeting for lead {lead_id}!")
        return {"success": False, "error": "BigQuery not available", "skipped": True}
    
    result = await service.persist_lead_status(
        lead_id=lead_id,
        status=LeadStatus.MEETING_SCHEDULED,
        user_info=user_info or {},
        lead_details=lead_details or {},
        meeting_details=meeting_details or {},
        research_data=research_data,
    )
    
    if result.get("success"):
        logger.info(f"✅ MEETING_SCHEDULED persisted successfully for lead {lead_id}")
    else:
        logger.error(f"❌ MEETING_SCHEDULED persistence FAILED for lead {lead_id}: {result.get('error')}")
    
    return result
