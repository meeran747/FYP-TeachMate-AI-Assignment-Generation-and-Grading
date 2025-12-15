from langgraph.graph import START, END, StateGraph
import logging
from typing import Optional, List, Dict, Any
from states import AssignmentGrade, Submissions, RubricGrade, SourceMatch
from supabase import create_client, Client
from prompts import assignment_grader
import json
import requests
import os
import tempfile
from pathlib import Path
import fitz  # PyMuPDF
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from llm_config import get_llm_model, get_llm_provider_info
from embedding_config import get_embeddings
from config import QDRANT_URL, QDRANT_API_KEY
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
import re
from urllib.parse import quote

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Supabase client (use service key to bypass RLS for grading)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("✓ Supabase client initialized for assignment grading (using service key)")
    except Exception as e:
        logger.error(f"❌ Could not initialize Supabase client: {e}")
else:
    logger.warning("⚠ Supabase not configured - SUPABASE_URL or SUPABASE_SERVICE_KEY not set")

# Initialize LLM model (configurable provider: OpenAI or Groq)
llm_provider_info = get_llm_provider_info()
logger.info(f"Using LLM provider for grading: {llm_provider_info['name']} ({llm_provider_info['provider']})")
if llm_provider_info.get('cost_effective'):
    logger.info("✓ Using cost-effective LLM provider!")
if llm_provider_info.get('fast'):
    logger.info("✓ Fast inference enabled!")

try:
    model = get_llm_model()
    logger.info("✓ LLM model initialized successfully for grading")
except Exception as e:
    logger.error(f"✗ Failed to initialize LLM model for grading: {str(e)}")
    logger.error("Please set LLM_PROVIDER environment variable (openai or groq)")
    logger.error(f"And set the corresponding API key: {llm_provider_info.get('api_key_env', 'API_KEY')}")
    logger.error(f"Get your API key from: {llm_provider_info.get('get_key_url', '')}")
    raise

grading_parser = JsonOutputParser(pydantic_object=RubricGrade)

def fetch_submission_ids(state: AssignmentGrade):
    """Fetch all submission IDs and file URLs for the given assignment ID from Supabase."""
    logger.info("=" * 60)
    logger.info("📥 FETCH_SUBMISSION_IDS NODE CALLED")
    
    if not supabase:
        logger.error("❌ Supabase client not initialized")
        return {"submission_ids": []}
    
    try:
        assignment_id = state['assignment_id']
        logger.info(f"   Assignment ID: {assignment_id}")
        logger.info(f"   Querying submissions table...")
        
        # Query the submissions table - filter by assignment_id and optionally by student_ids
        query = supabase.table('submissions').select('id, file_url, student_id').eq('assignment_id', assignment_id)
        
        # If student_ids are provided, filter to only those students (teacher's linked students)
        student_ids = state.get('student_ids')
        if student_ids and len(student_ids) > 0:
            logger.info(f"   Filtering to {len(student_ids)} teacher's students")
            query = query.in_('student_id', student_ids)
        else:
            logger.warning(f"   ⚠️ No student_ids provided - will grade ALL submissions for this assignment")
        
        response = query.execute()
        
        logger.info(f"   Raw response: {response}")
        logger.info(f"   Response data: {response.data}")
        logger.info(f"   Number of submissions found: {len(response.data) if response.data else 0}")
        
        if not response.data:
            logger.warning(f"⚠️ No submissions found for assignment {assignment_id}")
            return {"submission_ids": []}
        
        # Create Submissions objects from the response
        submissions = [
            Submissions(
                submission_id=submission['id'],
                file_url=submission['file_url']
            ) 
            for submission in response.data
        ]
        
        logger.info(f"Successfully fetched {len(submissions)} submission(s) for assignment {assignment_id}")
        logger.debug(f"Submissions: {submissions}")
        
        return {
            "submission_ids": submissions
        }
    except Exception as e:
        logger.error(f"Error fetching submission IDs: {str(e)}", exc_info=True)
        # Return empty list on error
        return {
            "submission_ids": []
        }

def fetch_rubric(state: AssignmentGrade):
    """Fetch the grading rubric for the given assignment ID from Supabase."""
    if not supabase:
        logger.error("Supabase client not initialized")
        return {"rubric": ""}
    
    try:
        assignment_id = state['assignment_id']
        logger.info(f"Fetching rubric for assignment_id: {assignment_id}")
        
        # Query the assignments table for the rubric with the given assignment_id
        response = supabase.table('assignments').select('rubric').eq('id', assignment_id).single().execute()
        
        rubric_data = response.data.get('rubric', {})
        
        # Parse the rubric JSON and format it as a structured string
        if isinstance(rubric_data, str):
            rubric_data = json.loads(rubric_data)
        
        total_points = rubric_data.get('total_points', 0)
        criteria = rubric_data.get('criteria', [])
        
        # Format rubric as a structured string
        rubric_string = f"Total Points: {total_points}\n\nGrading Criteria:\n"
        for i, criterion in enumerate(criteria, 1):
            rubric_string += f"{i}. {criterion}\n"
        
        logger.info(f"Successfully fetched rubric for assignment {assignment_id}")
        logger.debug(f"Rubric: {rubric_string}")
        
        return {
            "rubric": rubric_string
        }
    except Exception as e:
        logger.error(f"Error fetching rubric: {str(e)}")
        # Return empty string on error
        return {
            "rubric": ""
        }

def fetch_questions(state: AssignmentGrade):
    """Fetch the questions for the given assignment ID from Supabase."""
    if not supabase:
        logger.error("Supabase client not initialized")
        return {"questions": ""}
    
    try:
        assignment_id = state['assignment_id']
        logger.info(f"Fetching questions for assignment_id: {assignment_id}")
        
        # Query the assignments table for the questions with the given assignment_id
        response = supabase.table('assignments').select('questions').eq('id', assignment_id).single().execute()
        
        questions_data = response.data.get('questions', [])
        
        # Parse the questions if it's a string (JSON format)
        if isinstance(questions_data, str):
            questions_data = json.loads(questions_data)
        
        # Format questions as a structured string
        questions_string = "Assignment Questions:\n\n"
        for i, question in enumerate(questions_data, 1):
            questions_string += f"Question {i}: {question}\n\n"
        
        logger.info(f"Successfully fetched {len(questions_data)} question(s) for assignment {assignment_id}")
        logger.debug(f"Questions: {questions_string}")
        
        return {
            "questions": questions_string
        }
    except Exception as e:
        logger.error(f"Error fetching questions: {str(e)}")
        # Return empty string on error
        return {
            "questions": ""
        }

def download_and_parse_files(state: AssignmentGrade):
    """Download files from URLs, parse them (PDF or .py), and store content in file_content field."""
    try:
        submissions = state['submission_ids']
        logger.info(f"Processing {len(submissions)} submission file(s)")
        
        updated_submissions = []
        
        for submission in submissions:
            file_url = submission.file_url
            submission_id = submission.submission_id
            
            logger.info(f"Downloading file from: {file_url}")
            
            try:
                # Download the file
                response = requests.get(file_url, timeout=30)
                response.raise_for_status()
                
                # Determine file extension from URL or content-type
                file_extension = Path(file_url).suffix.lower()
                if not file_extension:
                    content_type = response.headers.get('content-type', '')
                    if 'pdf' in content_type:
                        file_extension = '.pdf'
                    elif 'python' in content_type or 'text' in content_type:
                        file_extension = '.py'
                
                # Create a temporary file
                with tempfile.NamedTemporaryFile(mode='wb', suffix=file_extension, delete=False) as temp_file:
                    temp_file.write(response.content)
                    temp_file_path = temp_file.name
                
                logger.info(f"File downloaded to temporary location: {temp_file_path}")
                
                # Parse the file based on its extension
                file_content = ""
                
                if file_extension == '.pdf':
                    # Parse PDF file using PyMuPDF
                    logger.info(f"Parsing PDF file for submission {submission_id}")
                    pdf_document = fitz.open(temp_file_path)
                    for page_num in range(len(pdf_document)):
                        page = pdf_document.load_page(page_num)
                        file_content += page.get_text()
                        logger.debug(f"Extracted text from page {page_num + 1}")
                    pdf_document.close()
                
                elif file_extension == '.py':
                    # Parse Python file (read as text)
                    logger.info(f"Reading Python file for submission {submission_id}")
                    with open(temp_file_path, 'r', encoding='utf-8') as py_file:
                        file_content = py_file.read()
                
                else:
                    # Try to read as text for any other file type
                    logger.warning(f"Unknown file extension {file_extension}, attempting to read as text")
                    try:
                        with open(temp_file_path, 'r', encoding='utf-8') as text_file:
                            file_content = text_file.read()
                    except Exception as text_error:
                        logger.error(f"Failed to read file as text: {str(text_error)}")
                        file_content = ""
                
                # Delete the temporary file
                os.unlink(temp_file_path)
                logger.info(f"Temporary file deleted: {temp_file_path}")
                
                # Update the submission with file content
                updated_submission = Submissions(
                    submission_id=submission_id,
                    file_url=file_url,
                    file_content=file_content,
                    plagerism_score=submission.plagerism_score,
                    total_score=submission.total_score
                )
                updated_submissions.append(updated_submission)
                
                logger.info(f"Successfully processed submission {submission_id} (content length: {len(file_content)} chars)")
                
            except requests.exceptions.RequestException as req_error:
                logger.error(f"Error downloading file for submission {submission_id}: {str(req_error)}")
                # Keep original submission without file_content
                updated_submissions.append(submission)
                
            except Exception as parse_error:
                logger.error(f"Error parsing file for submission {submission_id}: {str(parse_error)}")
                # Keep original submission without file_content
                updated_submissions.append(submission)
        
        logger.info(f"Completed processing all submission files")
        
        return {
            "submission_ids": updated_submissions
        }
        
    except Exception as e:
        logger.error(f"Error in download_and_parse_files: {str(e)}")
        # Return original submissions on error
        return {
            "submission_ids": state['submission_ids']
        }

def grade_submissions(state: AssignmentGrade):
    """Grade each submission using the AI grader with the rubric and questions."""
    try:
        submissions = state['submission_ids']
        questions = state['questions']
        rubric = state['rubric']
        
        logger.info(f"Starting grading process for {len(submissions)} submission(s)")
        
        # Create the prompt template
        prompt = PromptTemplate(
            template=assignment_grader,
            input_variables=["questions", "rubric", "submission"],
            partial_variables={"format_instructions": grading_parser.get_format_instructions()},
        )
        
        # Create the chain
        chain = prompt | model | grading_parser
        
        graded_submissions = []
        
        for i, submission in enumerate(submissions, 1):
            submission_id = submission.submission_id
            file_content = submission.file_content
            
            logger.info(f"Grading submission {i}/{len(submissions)} - ID: {submission_id}")
            
            try:
                # Skip if no file content
                if not file_content:
                    logger.warning(f"Skipping submission {submission_id} - no file content available")
                    graded_submissions.append(submission)
                    continue
                
                # Grade the submission
                result = chain.invoke({
                    "questions": questions,
                    "rubric": rubric,
                    "submission": file_content
                })
                
                logger.info(f"Raw grading result type: {type(result)}")
                logger.info(f"Raw grading result: {result}")
                
                # Handle both dict and Pydantic model formats
                if hasattr(result, 'total_score'):
                    # Pydantic model
                    grade = result.total_score
                    reason_text = result.reason
                    logger.info(f"Submission {submission_id} graded - Score: {grade} (from Pydantic model)")
                elif isinstance(result, dict):
                    # Dict format
                    if 'total_score' not in result:
                        raise ValueError(f"Grading result missing 'total_score' key. Result keys: {list(result.keys())}")
                    if 'reason' not in result:
                        raise ValueError(f"Grading result missing 'reason' key. Result keys: {list(result.keys())}")
                    grade = result['total_score']
                    reason_text = result['reason']
                    logger.info(f"Submission {submission_id} graded - Score: {grade} (from dict)")
                else:
                    raise ValueError(f"Unexpected grading result format: {type(result)}. Expected dict or RubricGrade model.")
                
                logger.debug(f"Grading reason: {reason_text[:200] if reason_text else 'None'}...")
                
                # Validate grade is not None
                if grade is None:
                    raise ValueError("Grade is None after grading. LLM may not have returned a valid score.")
                
                # Validate and potentially recalculate grade percentage
                # Try to extract points from reason text and recalculate if needed
                
                # Get total_points from rubric
                total_points = None
                if isinstance(rubric, dict):
                    total_points = rubric.get('total_points')
                elif hasattr(rubric, 'total_points'):
                    total_points = rubric.total_points
                
                if total_points:
                    # Try to extract points from reason text (look for patterns like "8/10", "8 out of 10", etc.)
                    import re
                    # Pattern to match "X/Y points" or "X/Y" or "X out of Y" - more comprehensive patterns
                    point_patterns = [
                        r'Question\s+\d+[:\s]+(\d+)\s*/\s*(\d+)\s*points?',  # "Question 1: 8/10 points"
                        r'(\d+)\s*/\s*(\d+)\s*points?',  # "8/10 points"
                        r'(\d+)\s*out\s*of\s*(\d+)\s*points?',  # "8 out of 10 points"
                        r'(\d+)\s*/\s*(\d+)',  # "8/10" (fallback)
                    ]
                    
                    points_earned = None
                    all_matches = []
                    for pattern in point_patterns:
                        matches = re.findall(pattern, reason_text, re.IGNORECASE)
                        if matches:
                            all_matches.extend(matches)
                    
                    if all_matches:
                        # Sum up all points found (take the earned points from each match)
                        total_earned = 0
                        for match in all_matches:
                            if len(match) == 2:
                                try:
                                    earned = int(match[0])
                                    max_pts = int(match[1])
                                    # Only add if it looks like a valid point breakdown (max_pts <= total_points)
                                    if max_pts <= total_points:
                                        total_earned += earned
                                except ValueError:
                                    continue
                        if total_earned > 0:
                            points_earned = total_earned
                            logger.info(f"   Extracted {points_earned} points from grading reason text")
                    
                    # If we found points, recalculate percentage
                    if points_earned is not None and total_points > 0:
                        calculated_percentage = (points_earned / total_points) * 100
                        # If the calculated percentage differs significantly from LLM's grade, use calculated
                        if abs(calculated_percentage - grade) > 5.0:  # More than 5% difference
                            logger.warning(f"   ⚠️ Grade mismatch detected! LLM gave {grade}%, but calculated {calculated_percentage}% from points ({points_earned}/{total_points})")
                            logger.info(f"   ✓ Using calculated percentage: {calculated_percentage}%")
                            grade = calculated_percentage
                            # Update reason to include the correction
                            reason_text = f"[Grade corrected from LLM calculation] {reason_text}"
                
                # Validate grade is a valid number
                try:
                    grade_float = float(grade)
                    if grade_float < 0 or grade_float > 100:
                        logger.warning(f"   ⚠️ Grade {grade_float} is outside valid range [0-100], clamping...")
                        grade_float = max(0.0, min(100.0, grade_float))
                        grade = grade_float
                except (ValueError, TypeError) as e:
                    logger.error(f"   ❌ Invalid grade value: {grade} (type: {type(grade)}). Error: {e}")
                    raise ValueError(f"Grade must be a number between 0 and 100, got: {grade}")
                
                # Create RubricGrade object
                rubric_grade = RubricGrade(
                    total_score=float(grade),
                    reason=reason_text or "No reason provided"
                )
                
                logger.info(f"   ✓ Created RubricGrade: total_score={rubric_grade.total_score}, reason_length={len(rubric_grade.reason)}")
                
                # Update the submission with the grade
                graded_submission = Submissions(
                    submission_id=submission_id,
                    file_url=submission.file_url,
                    file_content=file_content,
                    plagerism_score=submission.plagerism_score,
                    total_score=rubric_grade
                )
                
                logger.info(f"   ✓ Updated submission with grade. Submission.total_score type: {type(graded_submission.total_score)}")
                graded_submissions.append(graded_submission)
                
            except Exception as grading_error:
                error_type = type(grading_error).__name__
                error_msg = str(grading_error)
                
                logger.error(f"❌ Error grading submission {submission_id}: {error_msg}", exc_info=True)
                logger.error(f"   Error type: {error_type}")
                
                # Check for rate limit errors
                if "RateLimitError" in error_type or "429" in error_msg or "rate_limit" in error_msg.lower():
                    logger.error(f"   ⚠️ RATE LIMIT ERROR: The LLM API has hit its rate limit.")
                    logger.error(f"   This usually means you've exceeded your daily token quota.")
                    logger.error(f"   Please wait and try again later, or upgrade your API plan.")
                    # Still add submission without grade, but log the specific issue
                elif "timeout" in error_msg.lower() or "Timeout" in error_type:
                    logger.error(f"   ⚠️ TIMEOUT ERROR: The LLM API request timed out.")
                    logger.error(f"   This might be due to network issues or the API being slow.")
                else:
                    logger.error(f"   ⚠️ UNEXPECTED ERROR: An unexpected error occurred during grading.")
                
                # Keep original submission without grade on error
                graded_submissions.append(submission)
        
        logger.info(f"Completed grading all submissions")
        logger.info(f"   Total submissions processed: {len(graded_submissions)}")
        logger.info(f"   Submissions with grades: {sum(1 for s in graded_submissions if s.total_score)}")
        
        return {
            "submission_ids": graded_submissions
        }
        
    except Exception as e:
        logger.error(f"Error in grade_submissions: {str(e)}")
        # Return original submissions on error
        return {
            "submission_ids": state['submission_ids']
        }

def check_plagiarism(state: AssignmentGrade):
    """Check plagiarism by comparing similarity between all submissions.
    
    Compares teacher's submissions against ALL submissions for the assignment
    (not just teacher's students) to detect plagiarism across all students.
    
    If plagiarism score exceeds threshold (40%), the grade is set to 0.
    """
    PLAGIARISM_THRESHOLD = 40.0  # If similarity > 40%, set grade to 0
    
    try:
        submissions = state['submission_ids']
        assignment_id = state['assignment_id']
        logger.info(f"Starting plagiarism check for {len(submissions)} submission(s)")
        logger.info(f"   Plagiarism threshold: {PLAGIARISM_THRESHOLD}% (grade will be 0 if exceeded)")
        
        # Fetch ALL submissions for this assignment (not just teacher's students)
        # This is needed to check plagiarism against all submissions
        if not supabase:
            logger.error("Supabase client not initialized for plagiarism check")
            return {"submission_ids": submissions}
        
        logger.info(f"   Fetching ALL submissions for assignment {assignment_id} for plagiarism comparison")
        all_submissions_response = supabase.table('submissions').select('id, file_url').eq('assignment_id', assignment_id).execute()
        
        if not all_submissions_response.data:
            logger.warning("No submissions found for plagiarism check")
            return {"submission_ids": submissions}
        
        logger.info(f"   Found {len(all_submissions_response.data)} total submissions for comparison")
        
        # Download and parse all submission files for comparison
        all_submission_contents = {}
        for sub in all_submissions_response.data:
            sub_id = sub['id']
            file_url = sub['file_url']
            
            if not file_url:
                continue
                
            try:
                # Download the file
                response = requests.get(file_url, timeout=30)
                response.raise_for_status()
                
                # Parse as text (we already know these are .txt files)
                all_submission_contents[sub_id] = response.text
                logger.debug(f"   Downloaded content for submission {sub_id} ({len(response.text)} chars)")
            except Exception as e:
                logger.warning(f"   Could not download submission {sub_id} for plagiarism check: {e}")
        
        if len(all_submission_contents) < 2:
            logger.info("Less than 2 submissions with content - skipping plagiarism check")
            # Set plagiarism to 0 for all submissions
            updated_submissions = []
            for sub in submissions:
                updated_submission = Submissions(
                    submission_id=sub.submission_id,
                    file_url=sub.file_url,
                    file_content=sub.file_content,
                    plagerism_score=0.0,
                    total_score=sub.total_score
                )
                updated_submissions.append(updated_submission)
            return {"submission_ids": updated_submissions}
        
        updated_submissions = []
        
        # For each teacher's submission, compare with ALL submissions for the assignment
        for i, current_submission in enumerate(submissions):
            logger.info(f"Checking plagiarism for submission {i+1}/{len(submissions)} - ID: {current_submission.submission_id}")
            
            current_content = current_submission.file_content
            if not current_content:
                logger.warning(f"Submission {current_submission.submission_id} has no content - setting plagiarism score to 0")
                updated_submission = Submissions(
                    submission_id=current_submission.submission_id,
                    file_url=current_submission.file_url,
                    file_content=current_submission.file_content,
                    plagerism_score=0.0,
                    total_score=current_submission.total_score
                )
                updated_submissions.append(updated_submission)
                continue
            
            max_similarity = 0.0
            
            # Compare with ALL submissions for the assignment (not just teacher's students)
            for other_sub_id, other_content in all_submission_contents.items():
                if other_sub_id == current_submission.submission_id:  # Skip comparing with itself
                    continue
                
                if not other_content:
                    continue
                
                # Calculate simple similarity based on common words
                similarity = calculate_text_similarity(current_content, other_content)
                max_similarity = max(max_similarity, similarity)
                logger.debug(f"   Similarity with submission {other_sub_id}: {similarity * 100:.2f}%")
            
            # Convert to percentage
            plagiarism_percentage = round(max_similarity * 100, 2)
            logger.info(f"Submission {current_submission.submission_id} - Max similarity: {plagiarism_percentage}%")
            
            # Check against web sources and academic databases
            logger.info(f"   Checking against web sources and academic databases...")
            try:
                web_sources = check_web_sources(current_content, max_results=5)
            except Exception as e:
                logger.error(f"   Error in web source check: {e}", exc_info=True)
                web_sources = []
            
            try:
                academic_sources = check_academic_sources(current_content, max_results=5)
            except Exception as e:
                logger.error(f"   Error in academic source check: {e}", exc_info=True)
                academic_sources = []
            
            # Log summary
            logger.info(f"   Source check summary: {len(web_sources) if web_sources else 0} web sources, {len(academic_sources) if academic_sources else 0} academic sources")
            
            # Update plagiarism score if web/academic sources show high similarity
            if web_sources:
                max_web_similarity = max([s.similarity for s in web_sources])
                if max_web_similarity > plagiarism_percentage:
                    logger.info(f"   Higher similarity found in web sources: {max_web_similarity}%")
                    plagiarism_percentage = max_web_similarity
            
            if academic_sources:
                max_academic_similarity = max([s.similarity for s in academic_sources])
                if max_academic_similarity > plagiarism_percentage:
                    logger.info(f"   Higher similarity found in academic sources: {max_academic_similarity}%")
                    plagiarism_percentage = max_academic_similarity
            
            # Get the current grade
            current_grade = current_submission.total_score
            PLAGIARISM_THRESHOLD = 40.0  # If similarity > 40%, set grade to 0
            
            logger.info(f"   Current grade before plagiarism check: {current_grade.total_score if current_grade and hasattr(current_grade, 'total_score') else 'None'}")
            logger.info(f"   Final plagiarism score: {plagiarism_percentage}% (includes web/academic sources), Threshold: {PLAGIARISM_THRESHOLD}%")
            
            # If plagiarism exceeds threshold, set grade to 0
            if plagiarism_percentage > PLAGIARISM_THRESHOLD:
                logger.warning(f"   ⚠️ Plagiarism {plagiarism_percentage}% exceeds threshold {PLAGIARISM_THRESHOLD}% - setting grade to 0")
                
                # Get original score for logging
                original_score = 'N/A'
                if current_grade:
                    if hasattr(current_grade, 'total_score'):
                        original_score = current_grade.total_score
                    elif isinstance(current_grade, dict):
                        original_score = current_grade.get('total_score', 'N/A')
                
                # Always create a new grade with 0 (replace existing grade)
                zero_grade = RubricGrade(
                    total_score=0.0,
                    reason=f"Grade set to 0 due to high plagiarism score ({plagiarism_percentage}% similarity, threshold: {PLAGIARISM_THRESHOLD}%). Original grade was {original_score}."
                )
                current_grade = zero_grade
                logger.info(f"   ✓ Grade updated to 0 (was {original_score})")
            else:
                logger.info(f"   ✓ Plagiarism {plagiarism_percentage}% is below threshold - keeping original grade")
            
            # Update submission with plagiarism score, source attribution, and potentially modified grade
            updated_submission = Submissions(
                submission_id=current_submission.submission_id,
                file_url=current_submission.file_url,
                file_content=current_submission.file_content,
                plagerism_score=plagiarism_percentage,
                total_score=current_grade,
                web_sources=web_sources if web_sources else None,
                academic_sources=academic_sources if academic_sources else None
            )
            
            # Verify the grade was set correctly
            final_grade = updated_submission.total_score
            if final_grade:
                final_score = final_grade.total_score if hasattr(final_grade, 'total_score') else None
                logger.info(f"   Final grade in submission object: {final_score}, Plagiarism: {plagiarism_percentage}%")
                if plagiarism_percentage > PLAGIARISM_THRESHOLD and final_score != 0.0:
                    logger.error(f"   ❌ ERROR: Grade should be 0 but is {final_score}! Forcing to 0...")
                    updated_submission.total_score = RubricGrade(
                        total_score=0.0,
                        reason=f"Grade set to 0 due to high plagiarism score ({plagiarism_percentage}% similarity, threshold: {PLAGIARISM_THRESHOLD}%)."
                    )
            
            updated_submissions.append(updated_submission)
        
        logger.info("Completed plagiarism check for all submissions")
        # Log summary
        for sub in updated_submissions:
            grade_val = sub.total_score.total_score if sub.total_score and hasattr(sub.total_score, 'total_score') else None
            plag_val = sub.plagerism_score
            logger.info(f"   Submission {sub.submission_id}: Grade={grade_val}, Plagiarism={plag_val}%")
        
        return {
            "submission_ids": updated_submissions
        }
        
    except Exception as e:
        logger.error(f"Error in check_plagiarism: {str(e)}")
        # Return original submissions on error
        return {
            "submission_ids": state['submission_ids']
        }

def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two texts using Jaccard similarity.
    Returns a value between 0 and 1.
    """
    # Normalize texts: lowercase and split into words
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    # Calculate Jaccard similarity: intersection / union
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    if len(union) == 0:
        return 0.0
    
    similarity = len(intersection) / len(union)
    return similarity


def check_web_sources(text: str, max_results: int = 5) -> List[SourceMatch]:
    """
    Check submission text against web content using web search.
    Returns list of matched sources with URLs and similarity scores.
    """
    try:
        # Extract key phrases from text (first 200 chars for search query)
        search_query = text[:200].strip()
        if len(search_query) < 20:
            search_query = text[:500].strip()
        
        # Clean up the query
        search_query = re.sub(r'\s+', ' ', search_query)
        if len(search_query) > 200:
            sentences = re.split(r'[.!?]\s+', search_query)
            search_query = sentences[0] if sentences else search_query[:200]
        
        logger.info(f"   🔍 Searching web for: {search_query[:100]}...")
        
        # Try SerpAPI first if available (more reliable)
        serpapi_key = os.getenv("SERPAPI_API_KEY")
        if serpapi_key:
            try:
                serpapi_url = "https://serpapi.com/search"
                params = {
                    "engine": "google",
                    "q": search_query,
                    "api_key": serpapi_key,
                    "num": max_results
                }
                response = requests.get(serpapi_url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    web_sources = []
                    
                    if "organic_results" in data:
                        for result in data["organic_results"][:max_results]:
                            url = result.get("link", "")
                            title = result.get("title", "")
                            snippet = result.get("snippet", "")
                            
                            if url:
                                combined_text = (title + " " + snippet).lower()
                                similarity = calculate_text_similarity(text.lower(), combined_text)
                                
                                if similarity > 0.1:
                                    web_sources.append(SourceMatch(
                                        url=url,
                                        title=title,
                                        similarity=round(similarity * 100, 2),
                                        snippet=snippet[:200] if snippet else title[:200]
                                    ))
                    
                    logger.info(f"   ✓ Found {len(web_sources)} web sources via SerpAPI")
                    return web_sources
            except Exception as e:
                logger.warning(f"   SerpAPI error: {e}")
        
        # Fallback: Use DuckDuckGo (free, no API key)
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q={quote(search_query)}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(ddg_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(response.text, 'html.parser')
                    web_sources = []
                    
                    # Try multiple selectors as DuckDuckGo HTML structure may vary
                    results = soup.find_all('a', class_='result__a', limit=max_results)
                    if not results:
                        # Try alternative selector
                        results = soup.find_all('a', class_='web-result', limit=max_results)
                    if not results:
                        # Try finding links in result containers
                        result_containers = soup.find_all('div', class_='result', limit=max_results)
                        for container in result_containers:
                            link = container.find('a')
                            if link:
                                results.append(link)
                    
                    logger.debug(f"   DuckDuckGo returned {len(results)} raw results")
                    
                    for result in results:
                        url = result.get('href', '')
                        title = result.get_text(strip=True)
                        
                        if url and title:
                            similarity = calculate_text_similarity(text.lower(), title.lower())
                            if similarity > 0.1:
                                web_sources.append(SourceMatch(
                                    url=url,
                                    title=title,
                                    similarity=round(similarity * 100, 2),
                                    snippet=title[:200]
                                ))
                    
                    if web_sources:
                        logger.info(f"   ✓ Found {len(web_sources)} web sources via DuckDuckGo")
                    else:
                        logger.info(f"   ✓ Web search completed via DuckDuckGo (0 sources found with similarity > 10%)")
                    return web_sources[:max_results]
                except ImportError:
                    logger.warning("   BeautifulSoup not available - install with: pip install beautifulsoup4")
                    logger.info("   ✓ Web search skipped (BeautifulSoup not installed)")
                    return []
                except Exception as parse_error:
                    logger.warning(f"   Error parsing DuckDuckGo results: {parse_error}")
                    logger.info("   ✓ Web search completed (parsing error)")
                    return []
            else:
                logger.warning(f"   DuckDuckGo returned status {response.status_code}")
                logger.info("   ✓ Web search completed (HTTP error)")
                return []
        except Exception as e:
            logger.warning(f"   DuckDuckGo search error: {e}")
            logger.info("   ✓ Web search completed (request error)")
            return []
        
        logger.info("   ✓ Web search completed (no sources found)")
        return []
    except Exception as e:
        logger.error(f"Error checking web sources: {e}", exc_info=True)
        return []


def check_academic_sources(text: str, max_results: int = 5) -> List[SourceMatch]:
    """
    Check submission text against academic sources in Qdrant knowledge base.
    Returns list of matched academic sources with similarity scores.
    """
    try:
        if not QDRANT_URL or not QDRANT_API_KEY:
            logger.debug("   Qdrant not configured - skipping academic source check")
            return []
        
        logger.info(f"   📚 Searching academic sources in Qdrant knowledge base...")
        
        try:
            dense_embeddings = get_embeddings()
            sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
            
            qdrant = QdrantVectorStore.from_existing_collection(
                collection_name="teachmate",
                embedding=dense_embeddings,
                sparse_embedding=sparse_embeddings,
                retrieval_mode=RetrievalMode.HYBRID,
                url=QDRANT_URL,
                api_key=QDRANT_API_KEY,
                prefer_grpc=True,
            )
            
            # Search for similar content
            results = qdrant.similarity_search(text, k=max_results)
            
            academic_sources = []
            for doc in results:
                metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                source_url = metadata.get('source', metadata.get('url', 'knowledge_base'))
                title = metadata.get('title', 'Academic Source')
                
                similarity = calculate_text_similarity(text.lower(), doc.page_content.lower())
                
                if similarity > 0.1:
                    academic_sources.append(SourceMatch(
                        url=source_url,
                        title=title,
                        similarity=round(similarity * 100, 2),
                        snippet=doc.page_content[:200]
                    ))
            
            logger.info(f"   ✓ Found {len(academic_sources)} academic sources")
            return academic_sources
            
        except Exception as e:
            logger.warning(f"   Qdrant search error: {e}")
            return []
            
    except Exception as e:
        logger.error(f"Error checking academic sources: {e}", exc_info=True)
        return []

        

try:
    logger.info("Building assignment grading graph...")
    
    assignment_grader_builder = StateGraph(AssignmentGrade)

    # Add nodes to the graph
    assignment_grader_builder.add_node("fetch_submission_ids", fetch_submission_ids)
    assignment_grader_builder.add_node("fetch_rubric", fetch_rubric)
    assignment_grader_builder.add_node("fetch_questions", fetch_questions)
    assignment_grader_builder.add_node("download_and_parse_files", download_and_parse_files)
    assignment_grader_builder.add_node("grade_submissions", grade_submissions)
    assignment_grader_builder.add_node("check_plagiarism", check_plagiarism)

    # Connect the nodes in the workflow
    assignment_grader_builder.add_edge(START, "fetch_submission_ids")
    assignment_grader_builder.add_edge("fetch_submission_ids", "fetch_rubric")
    assignment_grader_builder.add_edge("fetch_rubric", "fetch_questions")
    assignment_grader_builder.add_edge("fetch_questions", "download_and_parse_files")
    assignment_grader_builder.add_edge("download_and_parse_files", "grade_submissions")
    assignment_grader_builder.add_edge("grade_submissions", "check_plagiarism")
    assignment_grader_builder.add_edge("check_plagiarism", END)

    assignment_grader_graph = assignment_grader_builder.compile()
    logger.info("Assignment grading graph compiled successfully")
    
except Exception as e:
    logger.error(f"Error building assignment grading graph: {str(e)}")
    raise


if __name__ == "__main__":
    try:
        logger.info("Starting assignment grading example...")
        
        example_input = {
            "assignment_id": "11745b7a-3933-4239-888f-4da4347483ee",
            "submission_ids": []
        }

        logger.info(f"Input: {example_input}")
        result = assignment_grader_graph.invoke(example_input)
        logger.info("Assignment grading completed successfully")
        print(result)
        
    except Exception as e:
        logger.error(f"Error during assignment grading: {str(e)}")
        raise
