"""
Embedding Configuration - Support for multiple embedding providers
You can switch between different embedding APIs here.
"""
import os
from typing import Optional

# Embedding provider options
EMBEDDING_PROVIDERS = {
    "huggingface": "Hugging Face (Free, Local)",
    "fastembed": "FastEmbed (Free, Local)",
    "openai": "OpenAI (Paid, API)",
    "cohere": "Cohere (Paid, API)",
    "google": "Google (Paid, API)",
}

# Get provider from environment or default to huggingface
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "huggingface").lower()

def get_embeddings():
    """
    Get embeddings based on configured provider.
    Returns the appropriate embedding class instance.
    """
    if EMBEDDING_PROVIDER == "huggingface":
        # Use community package (compatible with existing langchain version)
        from langchain_community.embeddings import HuggingFaceEmbeddings
        
        # Using a good free model that works well for RAG
        return HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},  # Use 'cuda' if you have GPU
            encode_kwargs={'normalize_embeddings': True}
        )
    
    elif EMBEDDING_PROVIDER == "fastembed":
        from langchain_community.embeddings import FastEmbedEmbeddings
        # FastEmbed is already installed and free
        return FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    
    elif EMBEDDING_PROVIDER == "openai":
        from langchain_openai import OpenAIEmbeddings
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set for OpenAI embeddings")
        return OpenAIEmbeddings(model="text-embedding-3-large")
    
    elif EMBEDDING_PROVIDER == "cohere":
        from langchain_community.embeddings import CohereEmbeddings
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            raise ValueError("COHERE_API_KEY not set for Cohere embeddings")
        return CohereEmbeddings(cohere_api_key=api_key)
    
    elif EMBEDDING_PROVIDER == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set for Google embeddings")
        return GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
    
    else:
        raise ValueError(f"Unknown embedding provider: {EMBEDDING_PROVIDER}. "
                        f"Available: {list(EMBEDDING_PROVIDERS.keys())}")

def get_provider_info():
    """Get information about the current provider."""
    return {
        "provider": EMBEDDING_PROVIDER,
        "name": EMBEDDING_PROVIDERS.get(EMBEDDING_PROVIDER, "Unknown"),
        "requires_api_key": EMBEDDING_PROVIDER in ["openai", "cohere", "google"],
        "is_free": EMBEDDING_PROVIDER in ["huggingface", "fastembed"]
    }

