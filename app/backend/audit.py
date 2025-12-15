"""
Audit Logging Module for TeachMate

Tracks:
- Who generated assignments
- What retrieval chunks were used
- What model was called
- Token cost estimation
- All user actions
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from supabase import Client
import os

logger = logging.getLogger(__name__)

# Supabase client for audit logging
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("✓ Supabase client initialized for audit logging")
    except Exception as e:
        logger.warning(f"Could not initialize Supabase client for audit: {e}")


def estimate_tokens(text: str) -> int:
    """Rough token estimation (1 token ≈ 4 characters)"""
    return len(text) // 4


def estimate_cost(provider: str, model: str, tokens: int, is_input: bool = True) -> float:
    """
    Estimate cost in USD based on provider and model.
    
    Pricing (approximate, as of 2024):
    - OpenAI GPT-4o: $2.50/$10 per 1M tokens (input/output)
    - Groq: Much cheaper, often free tier available
    """
    if provider.lower() == "openai":
        if "gpt-4o" in model.lower():
            rate = 2.50 if is_input else 10.0
        elif "gpt-4" in model.lower():
            rate = 30.0 if is_input else 60.0
        else:  # gpt-3.5-turbo
            rate = 0.50 if is_input else 1.50
        return (tokens / 1_000_000) * rate
    elif provider.lower() == "groq":
        # Groq is typically much cheaper or free tier
        return 0.0  # Often free or very low cost
    
    return 0.0


def log_assignment_creation(
    user_id: str,
    user_role: str,
    assignment_id: str,
    retrieval_chunks: Optional[List[Dict[str, Any]]] = None,
    model_called: Optional[str] = None,
    provider: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Log assignment creation with full audit trail.
    
    Args:
        user_id: ID of user who created assignment
        user_role: Role of user (teacher/admin)
        assignment_id: ID of created assignment
        retrieval_chunks: List of chunks retrieved from RAG
        model_called: Model name (e.g., 'gpt-4o', 'llama-3.3-70b')
        provider: Provider name ('openai', 'groq')
        input_tokens: Estimated input tokens
        output_tokens: Estimated output tokens
        metadata: Additional metadata
    """
    try:
        total_tokens = (input_tokens or 0) + (output_tokens or 0)
        cost = 0.0
        
        if model_called and provider:
            input_cost = estimate_cost(provider, model_called, input_tokens or 0, is_input=True)
            output_cost = estimate_cost(provider, model_called, output_tokens or 0, is_input=False)
            cost = input_cost + output_cost
        
        audit_data = {
            "user_id": user_id,
            "user_role": user_role,
            "action": "create_assignment",
            "resource_type": "assignment",
            "resource_id": assignment_id,
            "retrieval_chunks_used": retrieval_chunks or [],
            "model_called": model_called,
            "provider": provider,
            "token_estimate": total_tokens,
            "cost_estimate": cost,
            "metadata": {
                **(metadata or {}),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens
            }
        }
        
        if supabase:
            result = supabase.table("audit_logs").insert(audit_data).execute()
            logger.info(f"✓ Audit log created: {result.data[0]['id'] if result.data else 'unknown'}")
        else:
            # Fallback: log to console
            logger.info(f"AUDIT: {audit_data}")
            
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}", exc_info=True)


def log_submission(
    user_id: str,
    user_role: str,
    submission_id: str,
    assignment_id: str,
    metadata: Optional[Dict[str, Any]] = None
):
    """Log student submission."""
    try:
        audit_data = {
            "user_id": user_id,
            "user_role": user_role,
            "action": "submit_assignment",
            "resource_type": "submission",
            "resource_id": submission_id,
            "metadata": {
                **(metadata or {}),
                "assignment_id": assignment_id
            }
        }
        
        if supabase:
            supabase.table("audit_logs").insert(audit_data).execute()
            logger.info(f"✓ Submission audit log created")
        else:
            logger.info(f"AUDIT: {audit_data}")
            
    except Exception as e:
        logger.error(f"Failed to create submission audit log: {e}", exc_info=True)


def log_action(
    user_id: str,
    user_role: str,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """Generic action logger."""
    try:
        audit_data = {
            "user_id": user_id,
            "user_role": user_role,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "metadata": metadata or {}
        }
        
        if supabase:
            supabase.table("audit_logs").insert(audit_data).execute()
        else:
            logger.info(f"AUDIT: {audit_data}")
            
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}", exc_info=True)

