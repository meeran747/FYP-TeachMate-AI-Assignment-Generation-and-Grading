"""
LLM (Large Language Model) Configuration

This module provides a centralized way to select and configure LLM providers
for question generation and other AI tasks.

Supported Providers:
- OpenAI (gpt-4o, gpt-4, gpt-3.5-turbo)
- Groq (llama-3.3-70b-versatile, mixtral-8x7b-32768, gemma2-9b-it)

Usage:
    Set LLM_PROVIDER environment variable to "openai" or "groq"
    Set corresponding API key: OPENAI_API_KEY or GROQ_API_KEY
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def get_llm_model():
    """
    Get LLM model based on LLM_PROVIDER environment variable.
    
    Returns:
        LangChain LLM model instance
        
    Raises:
        ValueError: If provider is not supported or API key is missing
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    
    if provider == "groq":
        from langchain_openai import ChatOpenAI
        
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable not set!\n"
                "Get your API key from: https://console.groq.com/\n"
                "Then set it: export GROQ_API_KEY='your-api-key-here'"
            )
        
        # Groq models: llama-3.3-70b-versatile, mixtral-8x7b-32768, gemma2-9b-it
        model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        logger.info(f"Using Groq LLM: {model_name}")
        logger.info("✓ Groq is fast and cost-effective!")
        logger.info("✓ Using Groq's OpenAI-compatible API")
        
        # Groq uses OpenAI-compatible API endpoint
        return ChatOpenAI(
            model=model_name,
            temperature=0,
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )
    
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable not set!\n"
                "Get your API key from: https://platform.openai.com/\n"
                "Then set it: export OPENAI_API_KEY='your-api-key-here'"
            )
        
        model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
        logger.info(f"Using OpenAI LLM: {model_name}")
        return ChatOpenAI(
            model=model_name,
            temperature=0,
            api_key=api_key
        )
    
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: {provider}\n"
            "Supported providers: 'openai', 'groq'\n"
            "Set it with: export LLM_PROVIDER='groq' or 'openai'"
        )


def get_llm_provider_info():
    """
    Get information about the current LLM provider.
    
    Returns:
        dict with provider information
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    
    if provider == "groq":
        return {
            "provider": "groq",
            "name": "Groq",
            "is_free": False,  # Requires API key, but very affordable
            "cost_effective": True,
            "fast": True,
            "api_key_env": "GROQ_API_KEY",
            "get_key_url": "https://console.groq.com/"
        }
    elif provider == "openai":
        return {
            "provider": "openai",
            "name": "OpenAI",
            "is_free": False,
            "cost_effective": False,
            "fast": True,
            "api_key_env": "OPENAI_API_KEY",
            "get_key_url": "https://platform.openai.com/"
        }
    else:
        return {
            "provider": provider,
            "name": "Unknown",
            "is_free": False,
            "cost_effective": False,
            "fast": False,
            "api_key_env": "UNKNOWN",
            "get_key_url": ""
        }

