"""
SDR Research Module - Direct business research using Google Search and Gemini.

This module provides direct research capabilities for businesses found by the Lead Finder,
bypassing the full SDR agent workflow to provide quick insights.
"""

import os
import logging
import json
from typing import Dict, Any, Optional

import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger("SDRResearch")

# Get API key
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")


async def research_business(business_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Research a business using Google Search and Gemini AI.
    
    Args:
        business_data: Dictionary containing business information
            - name: Business name
            - address: Business address
            - city: City name
            - phone: Phone number (optional)
            - rating: Google rating (optional)
            - review_count: Number of reviews (optional)
    
    Returns:
        Dictionary containing research results with:
            - overview: Business overview
            - services: Services/products offered
            - online_presence: Current online presence analysis
            - pain_points: Identified pain points
            - opportunities: Website opportunities
            - competitors: Competitor analysis
            - recommendation: Why they need a website
    """
    
    business_name = business_data.get("name", "Unknown Business")
    business_address = business_data.get("address", "")
    business_city = business_data.get("city", "")
    business_phone = business_data.get("phone", "")
    business_rating = business_data.get("rating", 0)
    business_review_count = business_data.get("review_count", 0)
    
    logger.info(f"Researching business: {business_name} in {business_city}")
    
    if not GOOGLE_API_KEY:
        return {
            "success": False,
            "error": "Google API key not configured",
            "research": None
        }
    
    try:
        # Build the research prompt for Gemini
        research_prompt = f"""
You are a business research analyst. Analyze the following business and provide comprehensive insights.

## Business Information:
- **Name:** {business_name}
- **Address:** {business_address}
- **City:** {business_city}
- **Phone:** {business_phone or 'Not available'}
- **Google Rating:** {business_rating}/5 ({business_review_count} reviews)
- **Website:** This business does NOT have a website (that's why they're a lead)

## Your Task:
Research this business and provide a detailed analysis in the following JSON format:

{{
    "overview": "A 2-3 sentence overview of what this business likely does based on its name and location",
    "industry": "The industry/category this business belongs to",
    "target_customers": "Who are their likely customers",
    "services": ["List of services/products they likely offer"],
    "online_presence_analysis": {{
        "current_status": "Analysis of their current digital presence (no website)",
        "social_media_likely": "Whether they might have social media presence",
        "visibility_score": "low/medium/high - how visible they are online"
    }},
    "pain_points": [
        "Pain point 1 - related to not having a website",
        "Pain point 2 - related to losing customers to competitors",
        "Pain point 3 - related to credibility"
    ],
    "website_benefits": [
        "Specific benefit 1 for this type of business",
        "Specific benefit 2",
        "Specific benefit 3"
    ],
    "competitors_advantage": "How competitors with websites have an advantage",
    "recommendation": {{
        "priority": "high/medium/low",
        "reason": "Why this business should get a website soon",
        "suggested_features": ["Feature 1", "Feature 2", "Feature 3"]
    }},
    "conversation_starters": [
        "Opening line 1 for sales call",
        "Opening line 2 for sales call"
    ]
}}

Be specific to this business type and location. Make the analysis actionable for a sales team.
Respond ONLY with valid JSON, no markdown or extra text.
"""

        # Call Gemini API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={GOOGLE_API_KEY}",
                json={
                    "contents": [
                        {
                            "parts": [
                                {"text": research_prompt}
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.3,
                        "topP": 0.95,
                        "topK": 40,
                        "maxOutputTokens": 2048,
                        "responseMimeType": "application/json"
                    }
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Gemini API error: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": f"Gemini API error: {response.status_code}",
                    "research": None
                }
            
            result = response.json()
            
            # Extract the generated text
            try:
                generated_text = result["candidates"][0]["content"]["parts"][0]["text"]
                # Parse the JSON response
                research_data = json.loads(generated_text)
                
                logger.info(f"Successfully researched {business_name}")
                
                return {
                    "success": True,
                    "error": None,
                    "research": research_data,
                    "business_info": {
                        "name": business_name,
                        "address": business_address,
                        "city": business_city,
                        "phone": business_phone,
                        "rating": business_rating,
                        "review_count": business_review_count
                    }
                }
                
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                logger.error(f"Error parsing Gemini response: {e}")
                # Try to extract text even if not valid JSON
                if "candidates" in result:
                    raw_text = result["candidates"][0]["content"]["parts"][0].get("text", "")
                    return {
                        "success": True,
                        "error": None,
                        "research": {
                            "overview": raw_text,
                            "raw_response": True
                        },
                        "business_info": {
                            "name": business_name,
                            "address": business_address,
                            "city": business_city,
                            "phone": business_phone,
                            "rating": business_rating,
                            "review_count": business_review_count
                        }
                    }
                return {
                    "success": False,
                    "error": f"Error parsing response: {e}",
                    "research": None
                }
                
    except httpx.TimeoutException:
        logger.error(f"Timeout researching {business_name}")
        return {
            "success": False,
            "error": "Request timed out. Please try again.",
            "research": None
        }
    except Exception as e:
        logger.error(f"Error researching {business_name}: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "research": None
        }


async def generate_proposal(business_data: Dict[str, Any], research_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a sales proposal based on research data.
    
    Args:
        business_data: Business information
        research_data: Research results from research_business()
    
    Returns:
        Dictionary containing the generated proposal
    """
    
    business_name = business_data.get("name", "Unknown Business")
    
    if not GOOGLE_API_KEY:
        return {
            "success": False,
            "error": "Google API key not configured",
            "proposal": None
        }
    
    try:
        # Safely serialize data (handle datetime objects)
        def _safe_json(obj):
            if isinstance(obj, dict):
                return {k: _safe_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_safe_json(i) for i in obj]
            elif hasattr(obj, 'isoformat'):
                return obj.isoformat()
            elif isinstance(obj, Enum):
                return obj.value
            return obj

        proposal_prompt = f"""
You are a professional sales copywriter. Create a compelling, personalized sales proposal for website development services.

## Business Information:
{json.dumps(_safe_json(business_data), indent=2)}

## Research Findings:
{json.dumps(_safe_json(research_data), indent=2)}

## Your Task:
Write a short, personalized sales proposal (2-3 paragraphs) that:
1. Shows you understand their business
2. Highlights specific pain points they face without a website
3. Proposes concrete benefits tailored to their industry
4. Includes a clear call-to-action

The tone should be:
- Professional but friendly
- Confident but not pushy
- Specific to their business (not generic)

Respond with just the proposal text, no formatting or headers.
"""

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={GOOGLE_API_KEY}",
                json={
                    "contents": [
                        {
                            "parts": [
                                {"text": proposal_prompt}
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.5,
                        "topP": 0.95,
                        "topK": 40,
                        "maxOutputTokens": 1024
                    }
                }
            )
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Gemini API error: {response.status_code}",
                    "proposal": None
                }
            
            result = response.json()
            proposal_text = result["candidates"][0]["content"]["parts"][0]["text"]
            
            return {
                "success": True,
                "error": None,
                "proposal": proposal_text
            }
            
    except Exception as e:
        logger.error(f"Error generating proposal for {business_name}: {e}")
        return {
            "success": False,
            "error": str(e),
            "proposal": None
        }
