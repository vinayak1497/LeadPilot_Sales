"""
Email Reply Tracker Module
===========================

Monitors Gmail inbox for replies to sent proposals and automatically
confirms leads when positive responses are detected.

Features:
- IMAP-based email polling
- Keyword detection (YES, INTERESTED, CONFIRM, etc.)
- Reference code matching for accurate lead identification
- Real-time WebSocket notifications
"""

import asyncio
import imaplib
import email
from email.header import decode_header
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
import hashlib

logger = logging.getLogger("EmailTracker")

# Confirmation keywords to look for in replies
POSITIVE_KEYWORDS = [
    "yes", "interested", "confirm", "confirmed", "accept", "agree",
    "sounds good", "let's do it", "sign me up", "i'm in", "go ahead",
    "proceed", "approved", "okay", "ok", "sure", "absolutely",
    "definitely", "count me in", "let's proceed", "looking forward"
]

NEGATIVE_KEYWORDS = [
    "no", "not interested", "decline", "reject", "unsubscribe",
    "remove me", "stop", "no thanks", "not now", "maybe later"
]


class EmailReplyTracker:
    """
    Tracks email replies and automatically confirms leads based on positive responses.
    """
    
    def __init__(
        self,
        imap_server: str = "imap.gmail.com",
        email_address: str = None,
        email_password: str = None,
        check_interval: int = 30,  # seconds
        on_confirmation: Callable = None,
        on_rejection: Callable = None
    ):
        self.imap_server = imap_server
        self.email_address = email_address or os.getenv("EMAIL_USERNAME")
        self.email_password = email_password or os.getenv("EMAIL_PASSWORD")
        self.check_interval = check_interval
        self.on_confirmation = on_confirmation
        self.on_rejection = on_rejection
        
        self.is_running = False
        self._task = None
        self._pending_leads: Dict[str, dict] = {}  # reference_code -> lead_info
        self._processed_emails: set = set()  # Track already processed email IDs
        
        logger.info(f"EmailReplyTracker initialized for {self.email_address}")
    
    def generate_reference_code(self, business_id: str) -> str:
        """Generate a unique reference code for a business."""
        return hashlib.md5(f"{business_id}-confirm".encode()).hexdigest()[:8].upper()
    
    def register_pending_lead(self, business_id: str, business_name: str, business_data: dict = None):
        """Register a lead as pending confirmation via email."""
        reference_code = self.generate_reference_code(business_id)
        self._pending_leads[reference_code] = {
            "business_id": business_id,
            "business_name": business_name,
            "business_data": business_data or {},
            "sent_at": datetime.now().isoformat(),
            "status": "pending"
        }
        logger.info(f"Registered pending lead: {business_name} (ref: {reference_code})")
        return reference_code
    
    def get_pending_leads(self) -> Dict[str, dict]:
        """Get all pending leads awaiting confirmation."""
        return self._pending_leads.copy()
    
    async def start(self):
        """Start the background email checking task."""
        if self.is_running:
            logger.warning("Email tracker already running")
            return
        
        if not self.email_address or not self.email_password:
            logger.error("Email credentials not configured. Email tracking disabled.")
            return
        
        self.is_running = True
        self._task = asyncio.create_task(self._check_emails_loop())
        logger.info(f"Email reply tracking started (checking every {self.check_interval}s)")
    
    async def stop(self):
        """Stop the background email checking task."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Email reply tracking stopped")
    
    async def _check_emails_loop(self):
        """Main loop that periodically checks for email replies."""
        while self.is_running:
            try:
                await self._check_for_replies()
            except Exception as e:
                logger.error(f"Error checking emails: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    async def _check_for_replies(self):
        """Check inbox for new replies and process them."""
        if not self._pending_leads:
            return  # No pending leads to track
        
        try:
            # Connect to IMAP server
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email_address, self.email_password)
            mail.select("INBOX")
            
            # Search for recent emails (last 24 hours)
            date_since = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
            
            # Search for emails that could be replies to our proposals
            # Look for emails with "Re:" in subject or containing our reference codes
            status, messages = mail.search(None, f'(SINCE "{date_since}")')
            
            if status != "OK":
                logger.warning("Failed to search inbox")
                mail.close()
                mail.logout()
                return
            
            email_ids = messages[0].split()
            logger.debug(f"Found {len(email_ids)} recent emails to check")
            
            for email_id in email_ids[-50:]:  # Check last 50 emails max
                email_id_str = email_id.decode()
                
                # Skip already processed emails
                if email_id_str in self._processed_emails:
                    continue
                
                # Fetch email
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                if status != "OK":
                    continue
                
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # Get email details
                        subject = self._decode_header(msg["Subject"])
                        from_addr = self._decode_header(msg["From"])
                        body = self._get_email_body(msg)
                        
                        # Check if this is a reply to our proposal
                        if self._is_proposal_reply(subject, body):
                            logger.info(f"Found potential reply: '{subject}' from {from_addr}")
                            
                            # Find matching pending lead
                            matched_lead = self._match_reply_to_lead(subject, body)
                            
                            if matched_lead:
                                reference_code, lead_info = matched_lead
                                
                                # Determine response type
                                response_type = self._analyze_response(body)
                                
                                if response_type == "positive":
                                    logger.info(f"✅ Positive response detected for {lead_info['business_name']}")
                                    await self._handle_confirmation(reference_code, lead_info, from_addr, body)
                                elif response_type == "negative":
                                    logger.info(f"❌ Negative response detected for {lead_info['business_name']}")
                                    await self._handle_rejection(reference_code, lead_info, from_addr, body)
                                else:
                                    logger.info(f"⚠️ Unclear response for {lead_info['business_name']}")
                
                # Mark as processed
                self._processed_emails.add(email_id_str)
            
            mail.close()
            mail.logout()
            
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error: {e}")
        except Exception as e:
            logger.error(f"Error checking emails: {e}")
    
    def _decode_header(self, header_value: str) -> str:
        """Decode email header value."""
        if not header_value:
            return ""
        
        decoded_parts = decode_header(header_value)
        result = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result += part.decode(encoding or "utf-8", errors="ignore")
            else:
                result += part
        return result
    
    def _get_email_body(self, msg) -> str:
        """Extract plain text body from email message."""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
                    except:
                        pass
        else:
            try:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
            except:
                pass
        
        return body
    
    def _is_proposal_reply(self, subject: str, body: str) -> bool:
        """Check if email is a reply to our proposal."""
        subject_lower = subject.lower() if subject else ""
        body_lower = body.lower() if body else ""
        
        # Check for reply indicators
        is_reply = (
            "re:" in subject_lower or
            "lead proposal" in subject_lower or
            "website" in body_lower or
            any(code.lower() in body_lower for code in self._pending_leads.keys())
        )
        
        return is_reply
    
    def _match_reply_to_lead(self, subject: str, body: str) -> Optional[tuple]:
        """Match a reply to a pending lead."""
        subject_lower = subject.lower() if subject else ""
        body_lower = body.lower() if body else ""
        combined = subject_lower + " " + body_lower
        
        # First, try to match by reference code
        for code, lead_info in self._pending_leads.items():
            if code.lower() in combined:
                return (code, lead_info)
        
        # Then, try to match by business name
        for code, lead_info in self._pending_leads.items():
            business_name = lead_info.get("business_name", "").lower()
            if business_name and business_name in combined:
                return (code, lead_info)
        
        # Finally, if we only have one pending lead and it's a reply, assume it's for that lead
        if len(self._pending_leads) == 1 and "re:" in subject_lower:
            code = list(self._pending_leads.keys())[0]
            return (code, self._pending_leads[code])
        
        return None
    
    def _analyze_response(self, body: str) -> str:
        """Analyze email body to determine response type."""
        body_lower = body.lower() if body else ""
        
        # Count positive and negative indicators
        positive_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in body_lower)
        negative_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in body_lower)
        
        # Simple heuristic: more positive than negative = positive
        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        else:
            # Check for very clear indicators
            if any(word in body_lower.split() for word in ["yes", "interested", "confirm"]):
                return "positive"
            elif any(word in body_lower.split() for word in ["no", "unsubscribe"]):
                return "negative"
        
        return "unclear"
    
    async def _handle_confirmation(self, reference_code: str, lead_info: dict, from_addr: str, body: str):
        """Handle a confirmed lead."""
        lead_info["status"] = "confirmed"
        lead_info["confirmed_at"] = datetime.now().isoformat()
        lead_info["confirmed_by"] = from_addr
        lead_info["response_body"] = body[:500]  # Store first 500 chars of response
        
        if self.on_confirmation:
            try:
                await self.on_confirmation(lead_info)
            except Exception as e:
                logger.error(f"Error in confirmation callback: {e}")
        
        # Remove from pending leads
        if reference_code in self._pending_leads:
            del self._pending_leads[reference_code]
    
    async def _handle_rejection(self, reference_code: str, lead_info: dict, from_addr: str, body: str):
        """Handle a rejected lead."""
        lead_info["status"] = "rejected"
        lead_info["rejected_at"] = datetime.now().isoformat()
        lead_info["rejected_by"] = from_addr
        
        if self.on_rejection:
            try:
                await self.on_rejection(lead_info)
            except Exception as e:
                logger.error(f"Error in rejection callback: {e}")
        
        # Remove from pending leads
        if reference_code in self._pending_leads:
            del self._pending_leads[reference_code]
    
    def force_check(self):
        """Force an immediate check for replies (useful for testing)."""
        if self.is_running:
            asyncio.create_task(self._check_for_replies())


# Singleton instance for the application
email_tracker: Optional[EmailReplyTracker] = None


def get_email_tracker() -> Optional[EmailReplyTracker]:
    """Get the global email tracker instance."""
    return email_tracker


def init_email_tracker(on_confirmation: Callable = None, on_rejection: Callable = None) -> EmailReplyTracker:
    """Initialize the global email tracker instance."""
    global email_tracker
    email_tracker = EmailReplyTracker(
        on_confirmation=on_confirmation,
        on_rejection=on_rejection
    )
    return email_tracker
