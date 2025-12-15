"""
Document Ingestion Script for TeachMate RAG System
This script loads PDF files from the 'documents' folder and ingests them into Qdrant vector database.
"""
import os
import sys
from pathlib import Path
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import QDRANT_URL, QDRANT_API_KEY
from embedding_config import get_embeddings, get_provider_info
import logging

# Try to load from .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, skip

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_documents_folder():
    """Get the documents folder path (relative to this script)."""
    script_dir = Path(__file__).parent
    documents_folder = script_dir / "documents"
    return documents_folder

def load_pdf_files(folder_path: Path):
    """Load all PDF files from the specified folder."""
    all_docs = []
    
    if not folder_path.exists():
        logger.error(f"Documents folder not found: {folder_path}")
        logger.info(f"Please create the folder and add your PDF files: {folder_path}")
        return all_docs
    
    # Get all PDF files
    pdf_files = list(folder_path.glob("*.pdf"))
    
    if not pdf_files:
        logger.warning(f"No PDF files found in: {folder_path}")
        logger.info("Supported formats: .pdf")
        return all_docs
    
    logger.info(f"Found {len(pdf_files)} PDF file(s):")
    for pdf_file in pdf_files:
        logger.info(f"  - {pdf_file.name}")
    
    # Load each PDF file
    for pdf_file in pdf_files:
        logger.info(f"\nLoading: {pdf_file.name}")
        try:
            loader = PyMuPDFLoader(str(pdf_file))
            docs = loader.load()
            all_docs.extend(docs)
            logger.info(f"✓ Successfully loaded {len(docs)} pages from {pdf_file.name}")
        except Exception as e:
            logger.error(f"✗ Error loading {pdf_file.name}: {str(e)}")
    
    return all_docs

def split_documents(documents, chunk_size=1000, chunk_overlap=200):
    """Split documents into smaller chunks for better retrieval."""
    if not documents:
        return documents
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    
    logger.info(f"Splitting {len(documents)} documents into chunks...")
    split_docs = text_splitter.split_documents(documents)
    logger.info(f"Created {len(split_docs)} chunks")
    
    return split_docs

def ingest_to_qdrant(documents, collection_name="teachmate", batch_size=100):
    """Ingest documents into Qdrant vector database with batching and rate limiting."""
    if not documents:
        logger.error("No documents to ingest!")
        return False
    
    try:
        import time
        logger.info("Initializing embeddings...")
        provider_info = get_provider_info()
        logger.info(f"Using: {provider_info['name']}")
        
        try:
            dense_embeddings = get_embeddings()
            logger.info(f"✓ Embeddings initialized successfully")
        except Exception as emb_error:
            logger.error(f"✗ Failed to initialize embeddings: {emb_error}")
            logger.error(f"\nCurrent provider: {provider_info['provider']}")
            logger.error("\nTo switch providers, set EMBEDDING_PROVIDER environment variable:")
            logger.error("  export EMBEDDING_PROVIDER=huggingface  # Free, no API key")
            logger.error("  export EMBEDDING_PROVIDER=fastembed     # Free, no API key")
            logger.error("  export EMBEDDING_PROVIDER=openai        # Paid, requires API key")
            return False
        
        sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
        
        logger.info(f"Connecting to Qdrant and ingesting {len(documents)} documents...")
        logger.info(f"Collection name: {collection_name}")
        logger.info(f"Qdrant URL: {QDRANT_URL}")
        logger.info(f"Batch size: {batch_size} (to avoid rate limits)")
        
        # Check if collection exists, if not create it first with empty docs
        try:
            from qdrant_client import QdrantClient
            # Increase timeout for Qdrant client
            client = QdrantClient(
                url=QDRANT_URL, 
                api_key=QDRANT_API_KEY, 
                prefer_grpc=True,
                timeout=120  # 2 minute timeout
            )
            
            # Check if collection exists
            collections = client.get_collections().collections
            collection_exists = any(c.name == collection_name for c in collections)
            
            if not collection_exists:
                logger.info(f"Collection '{collection_name}' doesn't exist. Creating it...")
                # Create collection with first batch
                first_batch = documents[:min(batch_size, len(documents))]
                qdrant = QdrantVectorStore.from_documents(
                    first_batch,
                    dense_embeddings,
                    sparse_embedding=sparse_embeddings,
                    retrieval_mode=RetrievalMode.HYBRID,
                    url=QDRANT_URL,
                    prefer_grpc=True,
                    api_key=QDRANT_API_KEY,
                    collection_name=collection_name,
                )
                logger.info(f"✓ Created collection and added first {len(first_batch)} documents")
                documents = documents[len(first_batch):]
            else:
                logger.info(f"Collection '{collection_name}' already exists. Adding documents...")
                qdrant = QdrantVectorStore.from_existing_collection(
                    collection_name=collection_name,
                    embedding=dense_embeddings,
                    sparse_embedding=sparse_embeddings,
                    retrieval_mode=RetrievalMode.HYBRID,
                    url=QDRANT_URL,
                    api_key=QDRANT_API_KEY,
                    prefer_grpc=True,
                )
        except Exception as e:
            logger.warning(f"Could not check collection, proceeding with full ingestion: {e}")
            # Fallback to original method
            qdrant = QdrantVectorStore.from_documents(
                documents[:batch_size],  # Start with small batch
                dense_embeddings,
                sparse_embedding=sparse_embeddings,
                retrieval_mode=RetrievalMode.HYBRID,
                url=QDRANT_URL,
                prefer_grpc=True,
                api_key=QDRANT_API_KEY,
                collection_name=collection_name,
            )
            documents = documents[batch_size:]
        
        # Process remaining documents in batches
        if documents:
            total_batches = (len(documents) + batch_size - 1) // batch_size
            logger.info(f"Processing {len(documents)} remaining documents in {total_batches} batches...")
            
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                
                # Retry logic for network/timeout issues
                max_retries = 3
                retry_delay = 5  # seconds
                success = False
                
                for attempt in range(max_retries):
                    try:
                        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} documents)...")
                        if attempt > 0:
                            logger.info(f"  Retry attempt {attempt + 1}/{max_retries}")
                        
                        qdrant.add_documents(batch)
                        logger.info(f"✓ Batch {batch_num} completed")
                        success = True
                        break  # Success, exit retry loop
                        
                    except Exception as batch_error:
                        error_msg = str(batch_error)
                        
                        # Check for timeout/deadline errors
                        if "DEADLINE_EXCEEDED" in error_msg or "Deadline Exceeded" in error_msg or "timeout" in error_msg.lower():
                            if attempt < max_retries - 1:
                                wait_time = retry_delay * (attempt + 1)  # Exponential backoff
                                logger.warning(f"⚠ Timeout on batch {batch_num}, retrying in {wait_time} seconds...")
                                time.sleep(wait_time)
                                continue
                            else:
                                logger.error(f"✗ Batch {batch_num} failed after {max_retries} attempts (timeout)")
                                logger.error("This might be a network issue. You can:")
                                logger.error(f"  1. Resume later - {i} documents already processed")
                                logger.error("  2. Check your internet connection")
                                logger.error("  3. Try again - the script will skip already added documents")
                                return False
                        
                        # Check for quota/rate limit errors
                        elif "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
                            logger.error(f"✗ Rate limit/quota exceeded on batch {batch_num}")
                            logger.error("Solutions:")
                            logger.error("  1. Check your OpenAI billing/quota: https://platform.openai.com/account/billing")
                            logger.error("  2. Wait a few minutes and resume ingestion")
                            logger.error("  3. Reduce batch size (currently {})".format(batch_size))
                            logger.error(f"  4. Processed {i} documents so far. You can resume later.")
                            return False
                        
                        # Other errors
                        else:
                            if attempt < max_retries - 1:
                                wait_time = retry_delay * (attempt + 1)
                                logger.warning(f"⚠ Error on batch {batch_num}: {error_msg[:100]}")
                                logger.warning(f"  Retrying in {wait_time} seconds...")
                                time.sleep(wait_time)
                                continue
                            else:
                                logger.error(f"✗ Error in batch {batch_num}: {error_msg}")
                                logger.error(f"  Processed {i} documents before failure")
                                raise
                
                if not success:
                    return False
                
                # Rate limiting: wait between batches to avoid hitting quota
                if i + batch_size < len(documents):  # Don't wait after last batch
                    wait_time = 3  # 3 seconds between batches
                    logger.info(f"Waiting {wait_time} seconds before next batch...")
                    time.sleep(wait_time)
        
        logger.info(f"✓ Successfully ingested all documents into Qdrant!")
        logger.info(f"✓ Collection '{collection_name}' is ready for RAG queries")
        return True
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"✗ Error ingesting to Qdrant: {error_msg}")
        
        if "429" in error_msg or "quota" in error_msg.lower():
            logger.error("\n⚠️  OpenAI API Quota/Rate Limit Exceeded!")
            logger.error("Solutions:")
            logger.error("  1. Check your OpenAI billing: https://platform.openai.com/account/billing")
            logger.error("  2. Add payment method if needed")
            logger.error("  3. Wait a few minutes and try again")
            logger.error("  4. Reduce batch size in the script (currently {})".format(batch_size))
        else:
            logger.error("Make sure:")
            logger.error("  1. QDRANT_URL and QDRANT_API_KEY are correct in config.py")
            logger.error("  2. OpenAI API key is set (OPENAI_API_KEY environment variable)")
            logger.error("  3. You have internet connection")
        return False

def main():
    """Main ingestion function."""
    logger.info("=" * 60)
    logger.info("TeachMate Document Ingestion Script")
    logger.info("=" * 60)
    
    # Check embedding provider and API key requirements
    provider_info = get_provider_info()
    logger.info(f"\nEmbedding Provider: {provider_info['name']}")
    logger.info(f"Provider Type: {provider_info['provider']}")
    
    if provider_info['requires_api_key']:
        if provider_info['provider'] == 'openai':
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.error("OPENAI_API_KEY environment variable not set!")
                logger.info("\nTo fix this:")
                logger.info("  export OPENAI_API_KEY='your-key-here'")
                logger.info("  Or create .env file with: OPENAI_API_KEY=your-key-here")
                logger.info("\nGet your API key from: https://platform.openai.com/api-keys")
                sys.exit(1)
            logger.info(f"✓ OpenAI API key found (starts with: {api_key[:7]}...)")
        elif provider_info['provider'] == 'cohere':
            api_key = os.getenv("COHERE_API_KEY")
            if not api_key:
                logger.error("COHERE_API_KEY not set!")
                sys.exit(1)
        elif provider_info['provider'] == 'google':
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logger.error("GOOGLE_API_KEY not set!")
                sys.exit(1)
    else:
        logger.info("✓ Using FREE embedding provider - no API key needed!")
    
    # Get documents folder
    documents_folder = get_documents_folder()
    logger.info(f"\nDocuments folder: {documents_folder}")
    
    # Load PDF files
    documents = load_pdf_files(documents_folder)
    
    if not documents:
        logger.error("\nNo documents loaded. Cannot proceed with ingestion.")
        logger.info("\nTo fix this:")
        logger.info(f"  1. Create folder: {documents_folder}")
        logger.info("  2. Add your PDF files to that folder")
        logger.info("  3. Run this script again")
        sys.exit(1)
    
    logger.info(f"\n✓ Total documents loaded: {len(documents)} pages")
    
    # Split documents into chunks
    split_docs = split_documents(documents)
    
    # Ingest to Qdrant (with smaller batch size to avoid rate limits)
    logger.info("\n" + "=" * 60)
    # Use smaller batch size for large document sets to avoid rate limits
    batch_size = 50 if len(split_docs) > 1000 else 100
    logger.info(f"Using batch size: {batch_size} to avoid API rate limits")
    success = ingest_to_qdrant(split_docs, batch_size=batch_size)
    
    if success:
        logger.info("\n" + "=" * 60)
        logger.info("✓ Ingestion completed successfully!")
        logger.info("You can now create assignments using RAG.")
        logger.info("=" * 60)
    else:
        logger.error("\n" + "=" * 60)
        logger.error("✗ Ingestion failed. Please check the errors above.")
        logger.info("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()

