"""
BigQuery Persistence Service for LeadPilot.

Persists confirmed lead data to BigQuery with user context, 
status tracking, and meeting details.
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)

# BigQuery Configuration from environment
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "leadpilot-gdg")
DATASET_ID = os.environ.get("DATASET_ID", "leadpilot_dataset")
TABLE_ID = os.environ.get("TABLE_ID", "business_leads")
CREDENTIALS_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")

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
            logger.warning("BigQuery library not available. Persistence disabled.")
            return
        
        if not PROJECT_ID:
            logger.warning("GOOGLE_CLOUD_PROJECT not set. BigQuery persistence disabled.")
            return
        
        try:
            # Initialize client with project
            self.client = bigquery.Client(project=PROJECT_ID)
            self.dataset_ref = self.client.dataset(DATASET_ID)
            self.table_ref = self.dataset_ref.table(TABLE_ID)
            
            logger.info(f"BigQuery client initialized for project: {PROJECT_ID}")
            
            # Ensure dataset and table exist
            self._ensure_infrastructure()
            
        except Exception as e:
            logger.error(f"Failed to initialize BigQuery client: {e}")
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
        """Create the leads table with the proper schema."""
        if not self.client:
            return
        
        logger.info(f"Creating table {TABLE_ID}")
        
        schema = [
            # Lead Identification
            bigquery.SchemaField("lead_id", "STRING", mode="REQUIRED", 
                                 description="Unique lead identifier"),
            bigquery.SchemaField("place_id", "STRING", mode="NULLABLE",
                                 description="Google Places ID if available"),
            
            # User Information
            bigquery.SchemaField("user_id", "STRING", mode="REQUIRED",
                                 description="Authenticated user ID"),
            bigquery.SchemaField("user_email", "STRING", mode="NULLABLE",
                                 description="User email address"),
            bigquery.SchemaField("user_name", "STRING", mode="NULLABLE",
                                 description="User display name"),
            
            # Lead Status
            bigquery.SchemaField("status", "STRING", mode="REQUIRED",
                                 description="Lead status: ENGAGED_SDR, CONVERTING, MEETING_SCHEDULED"),
            bigquery.SchemaField("previous_status", "STRING", mode="NULLABLE",
                                 description="Previous status before update"),
            
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
            bigquery.SchemaField("business_review_count", "INTEGER", mode="NULLABLE",
                                 description="Number of reviews"),
            bigquery.SchemaField("business_website", "STRING", mode="NULLABLE",
                                 description="Business website URL"),
            
            # Research Data (stored as JSON string)
            bigquery.SchemaField("research_summary", "STRING", mode="NULLABLE",
                                 description="AI research summary"),
            bigquery.SchemaField("research_industry", "STRING", mode="NULLABLE",
                                 description="Identified industry"),
            bigquery.SchemaField("research_priority", "STRING", mode="NULLABLE",
                                 description="Lead priority: high, medium, low"),
            
            # Meeting Details (for MEETING_SCHEDULED status)
            bigquery.SchemaField("meeting_date", "DATE", mode="NULLABLE",
                                 description="Scheduled meeting date"),
            bigquery.SchemaField("meeting_time", "TIME", mode="NULLABLE",
                                 description="Scheduled meeting time"),
            bigquery.SchemaField("meeting_datetime", "TIMESTAMP", mode="NULLABLE",
                                 description="Full meeting datetime"),
            bigquery.SchemaField("meeting_calendar_link", "STRING", mode="NULLABLE",
                                 description="Calendar event link"),
            bigquery.SchemaField("meeting_notes", "STRING", mode="NULLABLE",
                                 description="Meeting notes or agenda"),
            
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
            bigquery.SchemaField("status_changed_at", "TIMESTAMP", mode="REQUIRED",
                                 description="When status was last changed"),
            
            # Additional Context
            bigquery.SchemaField("source", "STRING", mode="NULLABLE",
                                 description="Lead source (e.g., google_maps, manual)"),
            bigquery.SchemaField("notes", "STRING", mode="NULLABLE",
                                 description="Additional notes"),
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
        
        Args:
            lead_id: Unique identifier for the lead
            status: Current lead status
            user_info: Dict with user_id, email, name
            lead_details: Business information dict
            meeting_details: Optional meeting info (date, time, link)
            email_details: Optional email tracking info
            research_data: Optional AI research data
            previous_status: Previous status if known
            
        Returns:
            Dict with success status and any error message
        """
        if not self.client:
            logger.info("BigQuery client not available, skipping persistence")
            return {"success": False, "error": "BigQuery not configured"}
        
        try:
            now = datetime.utcnow()
            
            # Build the row data
            row = {
                "lead_id": str(lead_id),
                "place_id": lead_details.get("place_id"),
                
                # User info
                "user_id": str(user_info.get("user_id", "anonymous")),
                "user_email": user_info.get("email"),
                "user_name": user_info.get("name"),
                
                # Status
                "status": status.value,
                "previous_status": previous_status,
                
                # Business info
                "business_name": lead_details.get("name", "Unknown"),
                "business_phone": lead_details.get("phone"),
                "business_email": lead_details.get("email"),
                "business_address": lead_details.get("address"),
                "business_city": lead_details.get("city"),
                "business_category": lead_details.get("category"),
                "business_rating": float(lead_details["rating"]) if lead_details.get("rating") else None,
                "business_review_count": int(lead_details["review_count"]) if lead_details.get("review_count") else None,
                "business_website": lead_details.get("website"),
                
                # Timestamps
                "created_at": now.isoformat() + "Z",
                "updated_at": now.isoformat() + "Z",
                "status_changed_at": now.isoformat() + "Z",
                
                # Source
                "source": lead_details.get("source", "google_maps"),
                "notes": "; ".join(lead_details.get("notes", [])) if isinstance(lead_details.get("notes"), list) else lead_details.get("notes"),
            }
            
            # Add research data if available
            if research_data:
                row["research_summary"] = research_data.get("overview", "")[:5000]  # Limit size
                row["research_industry"] = research_data.get("industry")
                row["research_priority"] = research_data.get("recommendation", {}).get("priority")
            
            # Add email details if available
            if email_details:
                row["email_sent"] = True
                row["email_sent_at"] = email_details.get("sent_at", now.isoformat() + "Z")
                row["email_subject"] = email_details.get("subject")
            
            # Add meeting details if status is MEETING_SCHEDULED
            if status == LeadStatus.MEETING_SCHEDULED and meeting_details:
                if meeting_details.get("date"):
                    row["meeting_date"] = meeting_details["date"]
                if meeting_details.get("time"):
                    row["meeting_time"] = meeting_details["time"]
                if meeting_details.get("datetime"):
                    row["meeting_datetime"] = meeting_details["datetime"]
                row["meeting_calendar_link"] = meeting_details.get("calendar_link")
                row["meeting_notes"] = meeting_details.get("notes")
            
            # Insert row using streaming insert
            errors = self.client.insert_rows_json(
                self.table_ref,
                [row],
                row_ids=[f"{lead_id}_{status.value}_{now.timestamp()}"]
            )
            
            if errors:
                logger.error(f"BigQuery insert errors: {errors}")
                return {"success": False, "error": str(errors)}
            
            logger.info(f"✅ Lead {lead_id} persisted to BigQuery with status {status.value}")
            return {"success": True, "lead_id": lead_id, "status": status.value}
            
        except Exception as e:
            logger.error(f"Failed to persist lead to BigQuery: {e}", exc_info=True)
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
    """Persist when SDR engages with a lead."""
    service = get_bigquery_service()
    return await service.persist_lead_status(
        lead_id=lead_id,
        status=LeadStatus.ENGAGED_SDR,
        user_info=user_info,
        lead_details=lead_details,
        research_data=research_data,
    )


async def persist_lead_converting(
    lead_id: str,
    user_info: Dict[str, Any],
    lead_details: Dict[str, Any],
    email_details: Optional[Dict[str, Any]] = None,
    research_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist when a lead is confirmed/converting."""
    service = get_bigquery_service()
    return await service.persist_lead_status(
        lead_id=lead_id,
        status=LeadStatus.CONVERTING,
        user_info=user_info,
        lead_details=lead_details,
        email_details=email_details,
        research_data=research_data,
        previous_status="ENGAGED_SDR",
    )


async def persist_meeting_scheduled(
    lead_id: str,
    user_info: Dict[str, Any],
    lead_details: Dict[str, Any],
    meeting_details: Dict[str, Any],
    research_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist when a meeting is scheduled with a lead."""
    service = get_bigquery_service()
    return await service.persist_lead_status(
        lead_id=lead_id,
        status=LeadStatus.MEETING_SCHEDULED,
        user_info=user_info,
        lead_details=lead_details,
        meeting_details=meeting_details,
        research_data=research_data,
        previous_status="CONVERTING",
    )
