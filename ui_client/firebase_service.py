"""
Firebase Realtime Database Persistence Service for LeadPilot.

Uses the Firebase REST API via httpx (no Admin SDK needed).
This avoids service-account cross-project auth issues entirely.

Database structure:
  /users/{user_id}/
      profile: { email, name, picture, created_at, last_login, login_count }
      login_history/: [ { timestamp, ip, user_agent } ]
  /leads/{lead_id}/
      { ...lead fields, status_history/... }
  /user_leads/{user_id}/{lead_id}: { status, business_name, ... }  (index)

IMPORTANT: Firebase RTDB rules must allow read/write.
  Go to Firebase Console → Realtime Database → Rules, and set:
  {
    "rules": {
      ".read": true,
      ".write": true
    }
  }
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum

import httpx

logger = logging.getLogger(__name__)

# ── Firebase Configuration ─────────────────────────────────────────────
FIREBASE_DATABASE_URL = os.environ.get(
    "FIREBASE_DATABASE_URL",
    "https://leadpilot-b3c5d-default-rtdb.asia-southeast1.firebasedatabase.app"
).rstrip("/")

FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")


def _rtdb_url(path: str) -> str:
    """Build full RTDB REST endpoint URL."""
    path = path.strip("/")
    return f"{FIREBASE_DATABASE_URL}/{path}.json"


class LeadStatus(str, Enum):
    """Lead lifecycle statuses."""
    ENGAGED_SDR = "ENGAGED_SDR"
    CONVERTING = "CONVERTING"
    MEETING_SCHEDULED = "MEETING_SCHEDULED"
    CONFIRMED = "CONFIRMED"  # Final status when lead is fully confirmed


class FirebaseLeadService:
    """
    Async service using Firebase RTDB REST API via httpx.
    No Admin SDK or service account needed.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._client: Optional[httpx.AsyncClient] = None
        self._available = False
        self._initialized = True
        self._sync_init()

    def _sync_init(self):
        if not FIREBASE_DATABASE_URL:
            logger.warning("⚠️ FIREBASE_DATABASE_URL not set – persistence disabled")
            return
        try:
            self._client = httpx.AsyncClient(timeout=15.0)
            self._available = True
            logger.info(f"🔗 Firebase REST client ready → {FIREBASE_DATABASE_URL}")
        except Exception as e:
            logger.error(f"❌ Failed to create httpx client: {e}")

    # ── Low-level REST helpers ─────────────────────────────────────────

    async def _get(self, path: str) -> Any:
        url = _rtdb_url(path)
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def _put(self, path: str, data: Any) -> Any:
        url = _rtdb_url(path)
        resp = await self._client.put(url, json=_sanitize(data))
        resp.raise_for_status()
        return resp.json()

    async def _patch(self, path: str, data: dict) -> Any:
        url = _rtdb_url(path)
        resp = await self._client.patch(url, json=_sanitize(data))
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, data: Any) -> str:
        url = _rtdb_url(path)
        resp = await self._client.post(url, json=_sanitize(data))
        resp.raise_for_status()
        result = resp.json()
        return result.get("name", "") if isinstance(result, dict) else ""

    async def _delete(self, path: str):
        url = _rtdb_url(path)
        resp = await self._client.delete(url)
        resp.raise_for_status()

    def is_available(self) -> bool:
        return self._available

    # ==================================================================
    # User tracking
    # ==================================================================

    async def track_user_signin(
        self,
        user_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        picture: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a sign-in event and upsert user profile."""
        if not self._available:
            return {"success": False, "error": "Firebase not available", "skipped": True}

        try:
            now_iso = datetime.utcnow().isoformat() + "Z"
            safe_uid = _safe_key(user_id)

            existing = await self._get(f"/users/{safe_uid}/profile") or {}

            profile = {
                "user_id": user_id,
                "email": email or existing.get("email"),
                "name": name or existing.get("name"),
                "picture": picture or existing.get("picture"),
                "last_login": now_iso,
                "login_count": (existing.get("login_count") or 0) + 1,
                "created_at": existing.get("created_at") or now_iso,
            }

            await self._put(f"/users/{safe_uid}/profile", profile)

            await self._post(f"/users/{safe_uid}/login_history", {
                "timestamp": now_iso,
                "ip": ip_address,
                "user_agent": (user_agent or "")[:200],
            })

            logger.info(f"✅ User sign-in tracked: {user_id} ({email})")
            return {"success": True, "user_id": user_id}

        except Exception as e:
            logger.error(f"❌ Failed to track user sign-in: {e}")
            return {"success": False, "error": str(e)}

    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not self._available:
            return None
        try:
            safe_uid = _safe_key(user_id)
            return await self._get(f"/users/{safe_uid}/profile")
        except Exception as e:
            logger.error(f"Failed to get user profile: {e}")
            return None

    # ==================================================================
    # Lead persistence
    # ==================================================================

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
        """Persist a lead status update to Firebase RTDB."""
        if not self._available:
            return {"success": False, "error": "Firebase not available", "skipped": True}

        if not lead_id or not str(lead_id).strip():
            return {"success": False, "error": "lead_id is required"}

        try:
            now_iso = datetime.utcnow().isoformat() + "Z"
            safe_lead = _safe_key(str(lead_id).strip())

            logger.info(f"📝 Firebase write: lead={lead_id}, status={status.value}")

            existing_created = await self._get(f"/leads/{safe_lead}/created_at")

            lead_data: Dict[str, Any] = {
                "lead_id": str(lead_id).strip(),
                "current_status": status.value,
                "status": status.value,
                "business_name": str(lead_details.get("name", "Unknown")).strip() or "Unknown",
                "updated_at": now_iso,
                "created_at": existing_created or now_iso,
                "user_id": str(user_info.get("user_id", "anonymous")).strip() if user_info.get("user_id") else "anonymous",
                "user_email": user_info.get("email"),
                "user_name": user_info.get("name"),
                "business_phone": lead_details.get("phone"),
                "business_email": lead_details.get("email"),
                "business_address": lead_details.get("address"),
                "business_city": lead_details.get("city"),
                "business_category": lead_details.get("category"),
                "business_types": lead_details.get("types", []),
                "status_changed_at": now_iso,
            }

            rating = lead_details.get("rating")
            if rating is not None:
                try:
                    lead_data["business_rating"] = float(rating)
                except (ValueError, TypeError):
                    pass

            if research_data:
                overview = research_data.get("overview")
                if overview:
                    lead_data["research_summary"] = str(overview)[:5000]
                lead_data["research_industry"] = research_data.get("industry")
                rec = research_data.get("recommendation")
                if isinstance(rec, dict):
                    lead_data["research_priority"] = rec.get("priority")

            if email_details:
                lead_data["email_sent"] = True
                sent_at = email_details.get("sent_at")
                lead_data["email_sent_at"] = str(sent_at) if sent_at else now_iso
                lead_data["email_subject"] = email_details.get("subject")

            if status == LeadStatus.MEETING_SCHEDULED and meeting_details:
                if meeting_details.get("date"):
                    lead_data["meeting_date"] = str(meeting_details["date"])
                if meeting_details.get("time"):
                    lead_data["meeting_time"] = str(meeting_details["time"])
                lead_data["meeting_calendar_link"] = meeting_details.get("calendar_link")
                lead_data["meeting_meet_link"] = meeting_details.get("meet_link")
                lead_data["meeting_title"] = meeting_details.get("title")

            # Strip None values
            lead_data_clean = {k: v for k, v in lead_data.items() if v is not None}

            # Write lead
            await self._patch(f"/leads/{safe_lead}", lead_data_clean)

            # User→lead index
            uid = lead_data_clean.get("user_id", "anonymous")
            safe_uid = _safe_key(uid)
            await self._put(f"/user_leads/{safe_uid}/{safe_lead}", {
                "status": status.value,
                "business_name": lead_data_clean.get("business_name"),
                "business_city": lead_data_clean.get("business_city"),
                "updated_at": now_iso,
            })

            # Status history
            await self._post(f"/leads/{safe_lead}/status_history", {
                "status": status.value,
                "timestamp": now_iso,
                "previous_status": previous_status,
            })

            logger.info(f"✅ Firebase write OK → lead {lead_id} ({status.value})")
            return {"success": True, "lead_id": lead_id, "status": status.value}

        except Exception as e:
            logger.error(f"❌ Firebase persist error for {lead_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # ==================================================================
    # Queries
    # ==================================================================

    async def get_leads_by_user(
        self, user_id: str, status: Optional[LeadStatus] = None
    ) -> List[Dict[str, Any]]:
        """Get all leads for a user."""
        if not self._available:
            return []

        try:
            safe_uid = _safe_key(user_id)
            index = await self._get(f"/user_leads/{safe_uid}")

            if not index or not isinstance(index, dict):
                return []

            leads = []
            for lead_key in index.keys():
                lead_data = await self._get(f"/leads/{lead_key}")
                if lead_data and isinstance(lead_data, dict):
                    lead_data.pop("status_history", None)
                    if status and lead_data.get("status") != status.value:
                        continue
                    leads.append(lead_data)

            leads.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return leads[:100]

        except Exception as e:
            logger.error(f"Failed to query leads for {user_id}: {e}")
            return []

    async def get_lead_by_id(self, lead_id: str) -> Optional[Dict[str, Any]]:
        if not self._available:
            return None
        try:
            safe_id = _safe_key(lead_id)
            data = await self._get(f"/leads/{safe_id}")
            if data and isinstance(data, dict):
                data.pop("status_history", None)
            return data
        except Exception as e:
            logger.error(f"Failed to get lead {lead_id}: {e}")
            return None

    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Aggregate stats for a user's leads."""
        if not self._available:
            return {"total": 0, "by_status": {}, "cities": []}

        try:
            leads = await self.get_leads_by_user(user_id)
            by_status: Dict[str, int] = {}
            cities_set: set = set()

            for lead in leads:
                s = lead.get("status", "UNKNOWN")
                by_status[s] = by_status.get(s, 0) + 1
                city = lead.get("business_city")
                if city:
                    cities_set.add(city)

            return {
                "total": len(leads),
                "by_status": by_status,
                "cities": sorted(cities_set),
                "sdr_engaged": by_status.get("ENGAGED_SDR", 0),
                "converting": by_status.get("CONVERTING", 0),
                "meetings_scheduled": by_status.get("MEETING_SCHEDULED", 0),
                "converted": by_status.get("CONFIRMED", 0),  # CONFIRMED is the final status
            }
        except Exception as e:
            logger.error(f"Failed to get user stats: {e}")
            return {"total": 0, "by_status": {}, "cities": []}


# ── Helpers ────────────────────────────────────────────────────────────

def _safe_key(value: str) -> str:
    """Firebase RTDB keys cannot contain . $ # [ ] /"""
    if not value:
        return "unknown"
    for ch in ".#$[]/":
        value = value.replace(ch, "_")
    return value


def _sanitize(obj: Any) -> Any:
    """Recursively convert datetime/Enum objects so httpx JSON serializer can handle them."""
    if obj is None:
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(i) for i in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    return obj


# ── Singleton + drop-in helpers ────────────────────────────────────────

_fb_service: Optional[FirebaseLeadService] = None


def get_firebase_service() -> FirebaseLeadService:
    global _fb_service
    if _fb_service is None:
        _fb_service = FirebaseLeadService()
    return _fb_service


def get_bigquery_service() -> FirebaseLeadService:
    """Alias for backward compat."""
    return get_firebase_service()


async def persist_sdr_engaged(
    lead_id: str,
    user_info: Dict[str, Any],
    lead_details: Dict[str, Any],
    research_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not lead_id:
        return {"success": False, "error": "No lead_id", "skipped": True}
    logger.info(f"🔔 PERSIST: SDR_ENGAGED for lead {lead_id}")
    svc = get_firebase_service()
    if not svc.is_available():
        return {"success": False, "error": "Firebase not available", "skipped": True}
    return await svc.persist_lead_status(
        lead_id=lead_id, status=LeadStatus.ENGAGED_SDR,
        user_info=user_info or {}, lead_details=lead_details or {},
        research_data=research_data,
    )


async def persist_lead_converting(
    lead_id: str,
    user_info: Dict[str, Any],
    lead_details: Dict[str, Any],
    email_details: Optional[Dict[str, Any]] = None,
    research_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not lead_id:
        return {"success": False, "error": "No lead_id", "skipped": True}
    logger.info(f"🔔 PERSIST: CONVERTING for lead {lead_id}")
    svc = get_firebase_service()
    if not svc.is_available():
        return {"success": False, "error": "Firebase not available", "skipped": True}
    return await svc.persist_lead_status(
        lead_id=lead_id, status=LeadStatus.CONVERTING,
        user_info=user_info or {}, lead_details=lead_details or {},
        email_details=email_details, research_data=research_data,
    )


async def persist_meeting_scheduled(
    lead_id: str,
    user_info: Dict[str, Any],
    lead_details: Dict[str, Any],
    meeting_details: Dict[str, Any],
    research_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not lead_id:
        return {"success": False, "error": "No lead_id", "skipped": True}
    logger.info(f"🔔 PERSIST: MEETING_SCHEDULED for lead {lead_id}")
    svc = get_firebase_service()
    if not svc.is_available():
        return {"success": False, "error": "Firebase not available", "skipped": True}
    return await svc.persist_lead_status(
        lead_id=lead_id, status=LeadStatus.MEETING_SCHEDULED,
        user_info=user_info or {}, lead_details=lead_details or {},
        meeting_details=meeting_details or {}, research_data=research_data,
    )


async def persist_lead_confirmed(
    lead_id: str,
    user_info: Dict[str, Any],
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Mark a lead as fully confirmed (final status)."""
    if not lead_id:
        return {"success": False, "error": "No lead_id", "skipped": True}
    logger.info(f"🔔 PERSIST: CONFIRMED for lead {lead_id}")
    svc = get_firebase_service()
    if not svc.is_available():
        return {"success": False, "error": "Firebase not available", "skipped": True}
    
    try:
        now_iso = datetime.utcnow().isoformat() + "Z"
        safe_lead = _safe_key(str(lead_id).strip())
        
        # Get existing lead data
        existing_lead = await svc._get(f"/leads/{safe_lead}")
        if not existing_lead:
            return {"success": False, "error": "Lead not found"}
        
        previous_status = existing_lead.get("status", existing_lead.get("current_status"))
        
        # Update lead status to CONFIRMED
        update_data = {
            "current_status": LeadStatus.CONFIRMED.value,
            "status": LeadStatus.CONFIRMED.value,
            "confirmed_at": now_iso,
            "updated_at": now_iso,
            "status_changed_at": now_iso,
        }
        
        if note:
            update_data["confirmation_note"] = note
        
        await svc._patch(f"/leads/{safe_lead}", update_data)
        
        # Update user→lead index
        uid = existing_lead.get("user_id", "anonymous")
        safe_uid = _safe_key(uid)
        await svc._patch(f"/user_leads/{safe_uid}/{safe_lead}", {
            "status": LeadStatus.CONFIRMED.value,
            "updated_at": now_iso,
        })
        
        # Add to status history
        await svc._post(f"/leads/{safe_lead}/status_history", {
            "status": LeadStatus.CONFIRMED.value,
            "timestamp": now_iso,
            "previous_status": previous_status,
            "note": note,
        })
        
        logger.info(f"✅ Lead {lead_id} confirmed!")
        return {"success": True, "lead_id": lead_id, "status": LeadStatus.CONFIRMED.value}
        
    except Exception as e:
        logger.error(f"❌ Failed to confirm lead {lead_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def add_note_to_lead(
    lead_id: str,
    note: str,
    user_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Add a note to an existing lead."""
    if not lead_id:
        return {"success": False, "error": "No lead_id", "skipped": True}
    if not note:
        return {"success": False, "error": "No note provided"}
    
    logger.info(f"🔔 ADD NOTE to lead {lead_id}")
    svc = get_firebase_service()
    if not svc.is_available():
        return {"success": False, "error": "Firebase not available", "skipped": True}
    
    try:
        now_iso = datetime.utcnow().isoformat() + "Z"
        safe_lead = _safe_key(str(lead_id).strip())
        
        # Add note to the notes array
        note_data = {
            "text": note,
            "timestamp": now_iso,
            "user_email": user_info.get("email") if user_info else None,
        }
        
        await svc._post(f"/leads/{safe_lead}/notes", note_data)
        
        # Update the updated_at timestamp
        await svc._patch(f"/leads/{safe_lead}", {"updated_at": now_iso})
        
        logger.info(f"✅ Note added to lead {lead_id}")
        return {"success": True, "lead_id": lead_id}
        
    except Exception as e:
        logger.error(f"❌ Failed to add note to lead {lead_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def get_lead_full_details(lead_id: str) -> Optional[Dict[str, Any]]:
    """Get full lead details including meeting info and notes."""
    if not lead_id:
        return None
    
    svc = get_firebase_service()
    if not svc.is_available():
        return None
    
    try:
        safe_lead = _safe_key(str(lead_id).strip())
        lead_data = await svc._get(f"/leads/{safe_lead}")
        
        if not lead_data or not isinstance(lead_data, dict):
            return None
        
        # Get notes separately
        notes = await svc._get(f"/leads/{safe_lead}/notes")
        if notes and isinstance(notes, dict):
            # Convert Firebase object to list
            lead_data["notes"] = list(notes.values())
        
        # Get status history
        history = await svc._get(f"/leads/{safe_lead}/status_history")
        if history and isinstance(history, dict):
            lead_data["status_history"] = list(history.values())
        
        return lead_data
        
    except Exception as e:
        logger.error(f"Failed to get full lead details {lead_id}: {e}")
        return None


async def update_lead_status_by_column(
    lead_id: str,
    column_status: str,
    user_info: Optional[Dict[str, Any]] = None,
    lead_details: Optional[Dict[str, Any]] = None,
    meeting_details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Update lead status based on the dashboard column it's in."""
    if not lead_id:
        return {"success": False, "error": "No lead_id", "skipped": True}
    
    # Map dashboard column status to Firebase status
    status_map = {
        "sdr_engaged": LeadStatus.ENGAGED_SDR,
        "engaged": LeadStatus.ENGAGED_SDR,
        "sdr": LeadStatus.ENGAGED_SDR,
        "converting": LeadStatus.CONVERTING,
        "lead_manager": LeadStatus.CONVERTING,
        "confirmed": LeadStatus.CONVERTING,
        "meeting_scheduled": LeadStatus.MEETING_SCHEDULED,
        "meeting": LeadStatus.MEETING_SCHEDULED,
        "calendar": LeadStatus.MEETING_SCHEDULED,
    }
    
    column_lower = column_status.lower().strip()
    firebase_status = status_map.get(column_lower)
    
    if not firebase_status:
        logger.warning(f"Unknown column status: {column_status}, defaulting to CONVERTING")
        firebase_status = LeadStatus.CONVERTING
    
    svc = get_firebase_service()
    if not svc.is_available():
        return {"success": False, "error": "Firebase not available", "skipped": True}
    
    try:
        now_iso = datetime.utcnow().isoformat() + "Z"
        safe_lead = _safe_key(str(lead_id).strip())
        
        # Get existing lead to preserve data
        existing = await svc._get(f"/leads/{safe_lead}")
        previous_status = None
        if existing and isinstance(existing, dict):
            previous_status = existing.get("status", existing.get("current_status"))
        
        # Build update data
        update_data = {
            "current_status": firebase_status.value,
            "status": firebase_status.value,
            "updated_at": now_iso,
            "status_changed_at": now_iso,
        }
        
        # Add lead details if provided
        if lead_details:
            update_data["business_name"] = lead_details.get("name") or lead_details.get("business_name")
            update_data["business_phone"] = lead_details.get("phone")
            update_data["business_email"] = lead_details.get("email")
            update_data["business_address"] = lead_details.get("address")
            update_data["business_city"] = lead_details.get("city")
        
        # Add meeting details if status is meeting scheduled
        if firebase_status == LeadStatus.MEETING_SCHEDULED and meeting_details:
            update_data["meeting_date"] = meeting_details.get("date")
            update_data["meeting_time"] = meeting_details.get("time")
            update_data["meeting_calendar_link"] = meeting_details.get("calendar_link")
            update_data["meeting_meet_link"] = meeting_details.get("meet_link")
        
        # Add user info if provided
        if user_info:
            update_data["user_id"] = user_info.get("user_id", "anonymous")
            update_data["user_email"] = user_info.get("email")
        
        # Remove None values
        update_data = {k: v for k, v in update_data.items() if v is not None}
        
        await svc._patch(f"/leads/{safe_lead}", update_data)
        
        # Update user→lead index
        uid = update_data.get("user_id") or (existing.get("user_id") if existing else "anonymous") or "anonymous"
        safe_uid = _safe_key(uid)
        await svc._patch(f"/user_leads/{safe_uid}/{safe_lead}", {
            "status": firebase_status.value,
            "updated_at": now_iso,
        })
        
        # Add to status history
        await svc._post(f"/leads/{safe_lead}/status_history", {
            "status": firebase_status.value,
            "timestamp": now_iso,
            "previous_status": previous_status,
            "source": "column_update",
        })
        
        logger.info(f"✅ Lead {lead_id} status updated to {firebase_status.value} (from column: {column_status})")
        return {"success": True, "lead_id": lead_id, "status": firebase_status.value}
        
    except Exception as e:
        logger.error(f"❌ Failed to update lead status {lead_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
