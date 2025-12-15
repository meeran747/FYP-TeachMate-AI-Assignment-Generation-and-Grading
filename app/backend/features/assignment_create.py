from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import START, END, StateGraph
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
import asyncio
import logging
from langchain_core.prompts import PromptTemplate
from states import AssignmentCreate, AssignmentRelevanceCheck, AssignmentMaker, Rubric
from prompts import relevance_prompt, assignment_prompt, rubric_generator
from langchain_core.output_parsers import JsonOutputParser
from config import QDRANT_URL, QDRANT_API_KEY
from embedding_config import get_embeddings, get_provider_info
from llm_config import get_llm_model, get_llm_provider_info

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize LLM model (configurable provider: OpenAI or Groq)
llm_provider_info = get_llm_provider_info()
logger.info(f"Using LLM provider: {llm_provider_info['name']} ({llm_provider_info['provider']})")
if llm_provider_info.get('cost_effective'):
    logger.info("✓ Using cost-effective LLM provider!")
if llm_provider_info.get('fast'):
    logger.info("✓ Fast inference enabled!")

try:
    model = get_llm_model()
    logger.info("✓ LLM model initialized successfully")
except Exception as e:
    logger.error(f"✗ Failed to initialize LLM model: {str(e)}")
    logger.error("Please set LLM_PROVIDER environment variable (openai or groq)")
    logger.error(f"And set the corresponding API key: {llm_provider_info.get('api_key_env', 'API_KEY')}")
    logger.error(f"Get your API key from: {llm_provider_info.get('get_key_url', '')}")
    raise

relevance_parser = JsonOutputParser(pydantic_object=AssignmentRelevanceCheck)
assignment_parser = JsonOutputParser(pydantic_object=AssignmentMaker)
rubric_parser = JsonOutputParser(pydantic_object=Rubric)

# Initialize embeddings (configurable provider)
provider_info = get_provider_info()
logger.info(f"Using embedding provider: {provider_info['name']} ({provider_info['provider']})")
if provider_info['is_free']:
    logger.info("✓ Using FREE embedding provider - no API key needed!")
else:
    logger.info(f"⚠ Using PAID embedding provider - requires API key")

dense_embeddings = get_embeddings()
sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

# Connect to existing Qdrant collection (don't create from empty documents)
try:
    logger.info("Connecting to existing Qdrant collection 'teachmate'...")
    qdrant = QdrantVectorStore.from_existing_collection(
        collection_name="teachmate",
        embedding=dense_embeddings,
        sparse_embedding=sparse_embeddings,
        retrieval_mode=RetrievalMode.HYBRID,
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        prefer_grpc=True,
    )
    logger.info("Successfully connected to Qdrant collection 'teachmate'")
except Exception as e:
    logger.error(f"Error connecting to Qdrant: {str(e)}")
    logger.warning("Qdrant connection failed. The system will continue but context retrieval may fail.")
    # Set qdrant to None - will be handled in retrieve_context function
    qdrant = None

def retrieve_context(state: AssignmentCreate):
    """Retrieve relevant context from vector database based on assignment topic and description."""
    try:
        if qdrant is None:
            logger.warning("Qdrant not connected. Skipping context retrieval.")
            return {
                "context": ""
            }
        
        topic = state.get('topic', '')
        description = state.get('description', '')
        
        # Build a better search query by combining topic with key terms from description
        # Remove instructional phrases like "create an assignment", "write about", etc.
        import re
        
        # Start with the topic (most important)
        search_query = topic
        
        # Extract key terms from description, removing instructional phrases
        if description:
            # Remove common instructional phrases
            instructional_phrases = [
                r'create\s+an?\s+assignment',
                r'write\s+(an?\s+)?assignment',
                r'design\s+(an?\s+)?assignment',
                r'generate\s+(an?\s+)?assignment',
                r'covering',
                r'about',
                r'on\s+the\s+topic\s+of',
                r'related\s+to',
            ]
            
            cleaned_description = description
            for phrase in instructional_phrases:
                cleaned_description = re.sub(phrase, '', cleaned_description, flags=re.IGNORECASE)
            
            # Extract meaningful terms (words with 4+ characters, excluding common words)
            words = cleaned_description.split()
            meaningful_words = [w for w in words if len(w) >= 4 and w.lower() not in ['this', 'that', 'with', 'from', 'will', 'should', 'must']]
            
            if meaningful_words:
                # Add key terms from description to search query
                key_terms = ' '.join(meaningful_words[:10])  # Limit to first 10 meaningful words
                search_query = f"{topic} {key_terms}"
        
        logger.info(f"Retrieving context for topic: {topic}")
        logger.debug(f"Search query: {search_query[:200]}...")
        logger.debug(f"Original description: {description[:200]}...")
        
        # Retrieve more documents for better context (increased from 2 to 5)
        results = qdrant.similarity_search(
            search_query, k=5
        )
        
        # Convert results to string format
        context_string = "\n\n".join([doc.page_content for doc in results])
        state['context'] = context_string
        
        logger.info(f"Successfully retrieved {len(results)} documents from vector database")
        logger.debug(f"Context length: {len(context_string)} characters")
        logger.debug(f"Context preview: {context_string[:500]}...")
        
        return {
            "context": context_string
        }
    except Exception as e:
        logger.error(f"Error retrieving context: {str(e)}", exc_info=True)
        # Return empty context on error to allow workflow to continue
        return {
            "context": ""
        }    

def check_relevance(state: AssignmentCreate):
    """Check if the retrieved context is relevant to the assignment topic."""
    try:
        topic = state['topic']
        context = state['context']
        description = state.get('description', '')
        
        logger.info(f"Checking relevance for topic: {topic}")
        logger.debug(f"Description: {description[:200]}...")
        logger.debug(f"Context length: {len(context)} characters")
        logger.debug(f"Context preview: {context[:300]}...")
        
        # If context is empty, skip relevance check and allow assignment creation
        if not context or len(context.strip()) == 0:
            logger.warning("Context is empty - skipping relevance check, allowing assignment creation")
            return {
                "is_relevant": True,
                "reasoning": "No context retrieved, allowing assignment creation to proceed"
            }
        
        prompt = PromptTemplate(
            template=relevance_prompt,
            input_variables=["topic", "context"],
            partial_variables={"format_instructions": relevance_parser.get_format_instructions()},
        )
        
        chain = prompt | model | relevance_parser

        results = chain.invoke({"topic": topic, "context": context})
        
        logger.info(f"Relevance check completed - Is relevant: {results['is_relevant']}")
        logger.info(f"Reasoning: {results['reasoning']}")
        
        # If not relevant, log more details for debugging
        if not results['is_relevant']:
            logger.warning(f"⚠️ Context deemed irrelevant for topic '{topic}'")
            logger.warning(f"   Description was: {description[:200]}...")
            logger.warning(f"   Context preview: {context[:500]}...")
        
        return {
            "is_relevant": results['is_relevant'],
            "reasoning": results['reasoning']
        }
    except Exception as e:
        logger.error(f"Error checking relevance: {str(e)}", exc_info=True)
        # Default to relevant on error to allow assignment creation (better than blocking)
        logger.warning("Relevance check failed - defaulting to relevant to allow assignment creation")
        return {
            "is_relevant": True,
            "reasoning": f"Relevance check error occurred, allowing assignment creation: {str(e)}"
        }
    
def router(state: AssignmentCreate):
    """
    Router function that checks if the content is relevant to the assignment topic.
    Returns 'create_assignment' if relevant, 'end' if not relevant.
    """
    try:
        is_relevant = state.get('is_relevant', False)
        logger.info(f"Router decision - Is relevant: {is_relevant}")
        
        if is_relevant:
            logger.info("Routing to create_assignment")
            return "create_assignment"
        else:
            logger.info("Routing to end - content not relevant")
            return "end"
    except Exception as e:
        logger.error(f"Error in router function: {str(e)}")
        # Default to end on error for safety
        return "end"
       
def create_assignment(state: AssignmentCreate):
    """Create assignment questions based on the topic and description."""
    try:
        logger.info(f"Creating assignment for topic: {state['topic']} with {state['num_questions']} questions of type: {state['type']}")
        
        prompt = PromptTemplate(
            template=assignment_prompt,
            input_variables=["topic", "description", "type", "num_questions"],
            partial_variables={"format_instructions": assignment_parser.get_format_instructions()},
        )

        chain = prompt | model | assignment_parser

        results = chain.invoke({
            "topic": state['topic'], 
            "description": state['description'],
            "type": state['type'],
            "num_questions": state['num_questions']
        })

        logger.info(f"Successfully created {len(results['questions'])} assignment questions")
        logger.debug(f"Questions: {results['questions']}")

        return {
            "questions": results['questions']
        }
    except Exception as e:
        error_str = str(e)
        # Check if it's a rate limit error
        if "429" in error_str or "rate_limit" in error_str.lower() or "RateLimitError" in str(type(e)):
            logger.error(f"Rate limit error creating assignment: {error_str}")
            # Raise the error so it can be caught and handled properly
            raise Exception(f"API rate limit reached. Please try again later. Error: {error_str}")
        logger.error(f"Error creating assignment: {error_str}")
        # Return empty questions list on other errors
        return {
            "questions": []
        }

def rubric_generation(state: AssignmentCreate):
    """Generate a grading rubric based on the assignment questions."""
    try:
        logger.info(f"Generating rubric for {len(state['questions'])} questions")
        
        prompt = PromptTemplate(
            template=rubric_generator,
            input_variables=["questions"],
            partial_variables={"format_instructions": rubric_parser.get_format_instructions()},
        )

        chain = prompt | model | rubric_parser

        results = chain.invoke({
            "questions": state['questions']
        })

        logger.info(f"Rubric generated with total points: {results['total_points']}")
        logger.debug(f"Criteria: {results['criteria']}")

        return {
            "rubric": results
        }
    except Exception as e:
        error_str = str(e)
        # Check if it's a rate limit error
        if "429" in error_str or "rate_limit" in error_str.lower() or "RateLimitError" in str(type(e)):
            logger.error(f"Rate limit error generating rubric: {error_str}")
            # Raise the error so it can be caught and handled properly
            raise Exception(f"API rate limit reached. Please try again later. Error: {error_str}")
        logger.error(f"Error generating rubric: {error_str}")
        # Return empty rubric on other errors
        return {
            "rubric": {
                "total_points": 0,
                "criteria": []
            }
        }

try:
    logger.info("Building assignment creation graph...")
    
    assignment_builder = StateGraph(AssignmentCreate)

    assignment_builder.add_node("retrieve_context", retrieve_context)
    assignment_builder.add_node("check_relevance", check_relevance)
    assignment_builder.add_node("create_assignment", create_assignment)
    assignment_builder.add_node("rubric_generation", rubric_generation)

    assignment_builder.add_edge(START, "retrieve_context")
    assignment_builder.add_edge("retrieve_context", "check_relevance")

    # Add conditional edge based on relevance check
    assignment_builder.add_conditional_edges(
        "check_relevance",
        router,
        {
            "create_assignment": "create_assignment",
            "end": END
        }
    )

    assignment_builder.add_edge("create_assignment", "rubric_generation")
    assignment_builder.add_edge("rubric_generation", END)

    assignment_creator_graph = assignment_builder.compile()
    logger.info("Assignment creation graph compiled successfully")
    
except Exception as e:
    logger.error(f"Error building assignment creation graph: {str(e)}")
    raise

"""
# Example usage with logging
if __name__ == "__main__":
    try:
        logger.info("Starting assignment creation example...")
        
        example_input = {
            "topic": "Data warehousing and Data Lakes",
            "description": "Create an assignment on Data warehousing covering ETL processes, data storage solutions, and data retrieval methods.",
            "type": "multiple_choice",
            "num_questions": 2,
            "questions": [],
            "rubric": {},
        }

        logger.info(f"Input: {example_input}")
        result = assignment_creator_graph.invoke(example_input)
        logger.info("Assignment creation completed successfully")
        print(result)
        
    except Exception as e:
        logger.error(f"Error during assignment creation: {str(e)}")
        raise
"""