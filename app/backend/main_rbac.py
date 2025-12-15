"""
TeachMate Backend API with RBAC and Multi-Tenant Support

Endpoints:
- /create-assignment (teacher) - Create assignment with RAG
- /submit-assignment (student) - Submit assignment
- /get-my-assignments (student/teacher) - Get filtered assignments
- /get-submissions (teacher) - Get student submissions
- /admin/* (admin) - Admin endpoints
"""

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
import csv
import io
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging
import uvicorn
import os

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, skip

from features.assignment_create import assignment_creator_graph
from features.assignment_grade import assignment_grader_graph
from auth import get_current_user, UserContext, require_role
from audit import log_assignment_creation, log_submission, log_action
from db_helpers import (
    get_teacher_assignments, get_student_assignments,
    get_teacher_submissions, get_student_submissions,
    create_assignment_in_db, create_submission_in_db,
    get_user_profile, create_user_profile, get_user_by_email,
    find_teacher_by_email, update_submission_grade, get_teacher_students,
    update_assignment_in_db, delete_assignment_in_db,
    create_class, assign_teacher_to_class, enroll_student_in_class,
    get_teacher_classes, get_student_classes, get_class_students, get_class_teachers,
    get_class_by_code, is_student_enrolled,
    get_all_users, get_all_classes, get_all_assignments, get_all_submissions,
    get_system_stats, update_user_role, assign_teacher_to_class_admin,
    enroll_student_in_class_admin, remove_user_from_class, delete_user_profile,
    supabase as db_supabase
)
from analytics_helpers import get_assignment_analytics, get_overall_analytics

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="TeachMate Assignment Creator API (RBAC)",
    description="API for creating educational assignments using AI with multi-tenant RBAC",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================

class AssignmentRequest(BaseModel):
    topic: str = Field(..., description="The main topic for the assignment", example="Data Science")
    description: str = Field(..., description="Detailed description", example="Create an assignment covering ML algorithms")
    type: str = Field(..., description="Type of assignment", example="theoretical")
    num_questions: int = Field(..., ge=1, le=50, description="Number of questions", example=5)
    section: Optional[str] = Field(None, description="Section this assignment belongs to (optional - not used in class-based system)", example="CS-101-A")
    deadline: Optional[str] = Field(None, description="Deadline for the assignment (ISO format date string)")
    published: Optional[bool] = Field(False, description="Whether the assignment is published (visible to students)")
    class_id: Optional[str] = Field(None, description="Class ID this assignment belongs to (for multi-class system)")

class ClassRequest(BaseModel):
    name: str = Field(..., description="Class name", example="Mathematics")
    code: Optional[str] = Field(None, description="Class code", example="MATH-101")
    description: Optional[str] = Field(None, description="Class description")

class SubmissionRequest(BaseModel):
    assignment_id: str = Field(..., description="ID of assignment being submitted")
    roll_number: Optional[str] = Field(None, description="Student roll number")
    section: Optional[str] = Field(None, description="Student section")
    answer_text: Optional[str] = Field(None, description="Text answer")
    file_url: Optional[str] = Field(None, description="URL to uploaded file")

class AssignmentResponse(BaseModel):
    success: bool
    assignment_id: Optional[str] = None
    topic: str
    description: str
    type: str
    num_questions: int
    questions: List[Any]
    rubric: Optional[Dict[str, Any]] = None
    is_relevant: Optional[bool] = None
    relevance_reasoning: Optional[str] = None
    context_found: bool
    message: Optional[str] = None

class SubmissionResponse(BaseModel):
    success: bool
    submission_id: Optional[str] = None
    message: str

class HealthResponse(BaseModel):
    status: str
    message: str

class RegisterRequest(BaseModel):
    firstName: str = Field(..., description="First name")
    lastName: str = Field(..., description="Last name")
    email: str = Field(..., description="Email address")
    password: str = Field(..., description="Password")
    userType: str = Field(..., description="User type: 'student' or 'teacher'")
    section: Optional[str] = Field(None, description="Section (for teachers)")
    teacherEmail: Optional[str] = Field(None, description="Teacher email (for students)")
    roll_number: Optional[str] = Field(None, description="Roll number (for students)")

class RegisterResponse(BaseModel):
    success: bool
    message: str
    user: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class LoginRequest(BaseModel):
    email: str = Field(..., description="Email address")
    password: str = Field(..., description="Password")

class LoginResponse(BaseModel):
    success: bool
    message: str
    user: Optional[Dict[str, Any]] = None
    token: Optional[str] = None
    error: Optional[str] = None

# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "TeachMate Assignment Creator API (RBAC)",
        "version": "2.0.0",
        "status": "running",
        "features": ["RBAC", "Multi-tenant", "RAG", "Audit Logging"]
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        message="Assignment Creator API is running normally"
    )

# ============================================================
# AUTHENTICATION ENDPOINTS (Public - No auth required)
# ============================================================

@app.post("/register", response_model=RegisterResponse)
async def register(request: RegisterRequest):
    """
    Register a new user (Student or Teacher).
    
    This endpoint uses SUPABASE_SERVICE_KEY to bypass RLS and create the user profile.
    """
    try:
        # Check if user already exists
        existing_user = get_user_by_email(request.email)
        if existing_user:
            return RegisterResponse(
                success=False,
                message="User already exists",
                error="A user with this email already exists"
            )
        
        # For students: No teacher linking needed - students enroll in classes after signup
        # Class-based system: Students → Classes → Teachers (no direct teacher_id needed)
        student_section = None
        if request.userType == "student":
            # Section is optional - can be set later or when enrolling in classes
            student_section = request.section or None
            if request.teacherEmail:
                logger.info(f"Note: teacherEmail provided but not used - students link to teachers through classes")
            logger.info(f"Student registered - will enroll in classes using class codes after signup")
        
        # Step 1: Create user in Supabase Auth FIRST
        from supabase import create_client
        import os
        
        SUPABASE_URL = os.getenv("SUPABASE_URL", "")
        SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
        
        if not SUPABASE_URL:
            return RegisterResponse(
                success=False,
                message="Server configuration error",
                error="Supabase not configured"
            )
        
        # Use anon key for auth operations (sign_up requires anon key)
        supabase_key = SUPABASE_ANON_KEY if SUPABASE_ANON_KEY else os.getenv("SUPABASE_SERVICE_KEY", "")
        if not supabase_key:
            return RegisterResponse(
                success=False,
                message="Server configuration error",
                error="Supabase authentication not configured (need SUPABASE_ANON_KEY)"
            )
        
        supabase_auth = create_client(SUPABASE_URL, supabase_key)
        
        try:
            # Create user in Supabase Auth
            logger.info(f"Creating Supabase Auth user for: {request.email}")
            auth_response = supabase_auth.auth.sign_up({
                "email": request.email,
                "password": request.password
            })
            
            if not auth_response.user:
                return RegisterResponse(
                    success=False,
                    message="Registration failed",
                    error="Failed to create user in authentication system"
                )
            
            # Step 2: Use auth user's ID as the profile ID
            auth_user_id = auth_response.user.id
            logger.info(f"✓ Supabase Auth user created with ID: {auth_user_id}")
            
            # Step 2.5: Auto-confirm email using service role (bypasses email confirmation requirement)
            # This is needed because Supabase Auth requires email confirmation by default
            service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
            if service_key:
                try:
                    supabase_admin = create_client(SUPABASE_URL, service_key)
                    # Update user to confirm email using admin API
                    updated_user = supabase_admin.auth.admin.update_user_by_id(
                        auth_user_id,
                        {"email_confirm": True}
                    )
                    logger.info(f"✓ Email auto-confirmed for: {request.email}")
                except Exception as confirm_error:
                    logger.warning(f"Could not auto-confirm email: {confirm_error}")
                    logger.warning("User will need to confirm email via link before login")
            else:
                logger.warning("SUPABASE_SERVICE_KEY not set - email confirmation required")
            
            # Step 3: Create profile using service role key (bypasses RLS)
            logger.info(f"Creating user profile for: {request.email}")
            user_profile = create_user_profile(
                email=request.email,
                name=f"{request.firstName} {request.lastName}",
                role=request.userType,
                password=None,  # ⚠️ DO NOT store password - Supabase Auth handles it
                section=request.section if request.userType == "teacher" else student_section,
                teacher_id=None,  # No direct teacher linking - students link to teachers through classes
                user_id=auth_user_id,  # Use auth user ID
                roll_number=request.roll_number if request.userType == "student" else None
            )
            
            if not user_profile:
                error_msg = "Failed to create user profile. Check backend logs for details."
                logger.error(f"❌ Registration failed for {request.email}")
                # Try to delete auth user if profile creation failed
                try:
                    service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
                    if service_key:
                        supabase_admin = create_client(SUPABASE_URL, service_key)
                        supabase_admin.auth.admin.delete_user(auth_user_id)
                        logger.info(f"Cleaned up auth user: {auth_user_id}")
                except Exception as cleanup_error:
                    logger.warning(f"Could not cleanup auth user: {cleanup_error}")
                
                return RegisterResponse(
                    success=False,
                    message="Registration failed",
                    error=error_msg
                )
            
            logger.info(f"✓ User registered: {request.email} ({request.userType})")
            return RegisterResponse(
                success=True,
                message="User registered successfully",
                user=user_profile
            )
            
        except Exception as auth_error:
            logger.error(f"Supabase Auth registration failed: {auth_error}")
            # Check if user already exists in Auth
            if "already registered" in str(auth_error).lower() or "already exists" in str(auth_error).lower():
                return RegisterResponse(
                    success=False,
                    message="User already exists",
                    error="A user with this email already exists in the authentication system"
                )
            return RegisterResponse(
                success=False,
                message="Registration failed",
                error=f"Failed to create user: {str(auth_error)}"
            )
        
    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        return RegisterResponse(
            success=False,
            message="Registration failed",
            error=str(e)
        )


@app.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Login endpoint - uses Supabase Auth to get a real JWT access token.
    """
    try:
        from supabase import create_client
        import os
        
        SUPABASE_URL = os.getenv("SUPABASE_URL", "")
        SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")  # Use anon key for auth
        
        if not SUPABASE_URL:
            logger.error("SUPABASE_URL not configured")
            return LoginResponse(
                success=False,
                message="Server configuration error",
                error="Supabase not configured"
            )
        
        # Use anon key for auth operations (sign_in_with_password requires anon key)
        # If anon key not set, fall back to service key (but this may not work for auth)
        supabase_key = SUPABASE_ANON_KEY if SUPABASE_ANON_KEY else os.getenv("SUPABASE_SERVICE_KEY", "")
        
        if not supabase_key:
            logger.error("No Supabase key configured (need SUPABASE_ANON_KEY for auth)")
            return LoginResponse(
                success=False,
                message="Server configuration error",
                error="Supabase authentication not configured"
            )
        
        # Create Supabase client with anon key for auth
        supabase_auth = create_client(SUPABASE_URL, supabase_key)
        
        try:
            # Sign in with Supabase Auth to get a real JWT token
            auth_response = supabase_auth.auth.sign_in_with_password({
                "email": request.email,
                "password": request.password
            })
            
            # Verify we got a session with access_token
            if not auth_response.session:
                return LoginResponse(
                    success=False,
                    message="Authentication failed",
                    error="No session returned from Supabase Auth"
                )
            
            if not auth_response.session.access_token:
                return LoginResponse(
                    success=False,
                    message="Authentication failed",
                    error="No access token in session"
                )
            
            # Get the REAL Supabase JWT tokens (format: xxxx.yyyy.zzzz)
            access_token = auth_response.session.access_token  # Real JWT: xxxx.yyyy.zzzz
            refresh_token = auth_response.session.refresh_token if hasattr(auth_response.session, 'refresh_token') else None
            
            # Get user profile from database
            user = get_user_by_email(request.email)
            
            if not user:
                return LoginResponse(
                    success=False,
                    message="User profile not found",
                    error="User profile does not exist"
                )
            
            logger.info(f"✓ User logged in via Supabase Auth: {request.email} ({user['role']})")
            logger.info(f"✓ Returning REAL Supabase JWT access_token (length: {len(access_token)}, format: {access_token[:20]}...)")
            
            # Return the REAL Supabase JWT token (NOT a custom token)
            return LoginResponse(
                success=True,
                message="Login successful",
                user=user,
                token=access_token  # Real Supabase JWT token (format: xxxx.yyyy.zzzz)
            )
                
        except Exception as auth_error:
            error_msg = str(auth_error)
            logger.error(f"Supabase Auth sign-in failed: {auth_error}")
            
            # Provide helpful error messages
            if "Email not confirmed" in error_msg or "email_not_confirmed" in error_msg.lower():
                return LoginResponse(
                    success=False,
                    message="Email not confirmed",
                    error="Please confirm your email address before logging in. Check your inbox for the confirmation link."
                )
            elif "Invalid login credentials" in error_msg or "invalid_credentials" in error_msg.lower():
                return LoginResponse(
                    success=False,
                    message="Invalid credentials",
                    error="Invalid email or password"
                )
            else:
                return LoginResponse(
                    success=False,
                    message="Authentication failed",
                    error=f"Login failed: {error_msg}"
                )
        
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return LoginResponse(
            success=False,
            message="Login failed",
            error=str(e)
        )

# ============================================================
# TEACHER ENDPOINTS
# ============================================================

@app.post("/create-assignment", response_model=AssignmentResponse)
async def create_assignment(
    request: AssignmentRequest,
    user: UserContext = Depends(get_current_user)
):
    """
    Create an educational assignment (Teacher only).
    
    This endpoint:
    1. Verifies user is a teacher
    2. Retrieves relevant context from knowledge base
    3. Creates assignment questions using RAG
    4. Saves to database with proper tenant isolation
    5. Logs audit trail
    """
    # Check role
    if not user.is_teacher() and not user.is_admin():
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can create assignments"
        )
    
    try:
        logger.info(f"Teacher {user.email} creating assignment: {request.topic}")
        
        # Get user profile to get section
        profile = get_user_profile(user.user_id)
        
        # Handle dev mode (bypassed auth)
        # Check if it's the dev user UUID (00000000-0000-0000-0000-000000000001)
        dev_user_id = "00000000-0000-0000-0000-000000000001"
        is_dev_user = user.user_id == dev_user_id or user.user_id == "dev-user-id"
        if not profile and is_dev_user:
            # Use request section or default
            section = request.section or None  # Optional - not used in class-based system
            logger.warning("⚠️ Dev mode: Using default section")
            
            # For dev mode, we need to ensure the dev user exists in the database
            # or use a valid UUID. Let's create/use a dev profile if needed.
            try:
                # Normalize dev user ID to valid UUID
                if user.user_id == "dev-user-id":
                    user.user_id = dev_user_id
                
                # Try to get dev profile by UUID first
                dev_profile = get_user_profile(dev_user_id)
                
                # If not found by UUID, try to find by email (in case it exists with different ID)
                if not dev_profile:
                    logger.info(f"Dev profile not found by UUID, checking by email: {user.email}")
                    existing_user = get_user_by_email(user.email)
                    if existing_user:
                        logger.info(f"Found existing dev user with ID: {existing_user['id']}, updating to use dev UUID...")
                        # Use the existing user's ID instead of creating a new one
                        user.user_id = existing_user['id']
                        profile = existing_user
                        logger.info(f"✓ Using existing dev user profile with ID: {user.user_id}")
                    else:
                        # Create new dev profile
                        logger.info("Creating dev user profile in database...")
                        dev_profile = create_user_profile(
                            email=user.email,
                            name=user.name,
                            role=user.role,
                            section=section,
                            user_id=dev_user_id
                        )
                        if dev_profile:
                            profile = dev_profile
                            user.user_id = dev_user_id  # Ensure we use the dev UUID
                            logger.info("✓ Dev user profile created")
                else:
                    profile = dev_profile
                    user.user_id = dev_user_id  # Ensure we use the dev UUID
            except Exception as e:
                logger.warning(f"Could not create/find dev profile: {e}")
                # Still proceed with dev_user_id for assignment creation
                user.user_id = dev_user_id
        elif not profile:
            raise HTTPException(status_code=404, detail="User profile not found")
        else:
            # Section is optional - use from request if provided, otherwise None
            section = request.section if request.section else None
        
        # Prepare input state for the graph
        input_state = {
            "topic": request.topic,
            "description": request.description,
            "type": request.type,
            "num_questions": request.num_questions,
            "questions": [],
            "rubric": {},
            "context": "",
            "is_relevant": None,
            "relevance_reasoning": None
        }
        
        # Execute the assignment creation graph
        try:
            result = assignment_creator_graph.invoke(input_state)
        except Exception as e:
            error_str = str(e)
            # Check if it's a rate limit error
            if "429" in error_str or "rate_limit" in error_str.lower() or "RateLimitError" in error_str:
                logger.error(f"Rate limit error during assignment creation: {error_str}")
                raise HTTPException(
                    status_code=429,
                    detail="API rate limit reached. The AI service has reached its daily token limit. Please try again later or upgrade your API plan."
                )
            # Re-raise other errors
            raise
        
        # Extract results
        questions_created = result.get("questions", [])
        rubric = result.get("rubric", {})
        is_relevant = result.get("is_relevant", False)
        context_found = bool(result.get("context", "").strip())
        
        success = len(questions_created) > 0
        
        # Save to database if successful
        assignment_id = None
        db_save_failed = False
        if success:
            logger.info(f"💾 Attempting to save assignment to database...")
            assignment_id = create_assignment_in_db(
                teacher_id=user.user_id,
                section=section,
                topic=request.topic,
                description=request.description,
                assignment_type=request.type,
                num_questions=request.num_questions,
                questions=questions_created,
                rubric=rubric,
                published=request.published if hasattr(request, 'published') else False,  # Use request published status, default to draft
                deadline=request.deadline,
                class_id=request.class_id
            )
            
            if assignment_id:
                logger.info(f"✓ Assignment saved with ID: {assignment_id}")
            else:
                logger.error(f"❌ Failed to save assignment to database!")
                db_save_failed = True
                # Don't set assignment_id, so frontend knows it wasn't saved
            
            # Log audit trail only if assignment was successfully saved
            if assignment_id:
                # TODO: Extract retrieval chunks from result
                retrieval_chunks = []  # Should be extracted from RAG result
                model_called = os.getenv("LLM_PROVIDER", "openai")
                provider = os.getenv("LLM_PROVIDER", "openai")
                
                log_assignment_creation(
                    user_id=user.user_id,
                    user_role=user.role,
                    assignment_id=assignment_id,
                    retrieval_chunks=retrieval_chunks,
                    model_called=model_called,
                    provider=provider,
                    metadata={
                        "topic": request.topic,
                        "section": section,
                        "num_questions": request.num_questions
                    }
                )
        
        # Prepare response
        message = None
        if not success and len(questions_created) == 0:
            # Check if this might be due to rate limits (empty questions but no error raised)
            message = "Failed to generate assignment questions. This may be due to API rate limits. Please try again later or check your API configuration."
        elif db_save_failed:
            message = f"Questions generated but failed to save to database. Please check your Supabase configuration (SUPABASE_URL and SUPABASE_SERVICE_KEY)."
        elif not context_found:
            message = "No relevant context found in the knowledge base."
        elif not is_relevant:
            message = "Content was not deemed relevant to the topic."
        elif not success:
            message = "Assignment creation failed."
        else:
            message = f"Successfully created {len(questions_created)} questions."
        
        return AssignmentResponse(
            success=success,
            assignment_id=assignment_id,
            topic=request.topic,
            description=request.description,
            type=request.type,
            num_questions=request.num_questions,
            questions=questions_created,
            rubric=rubric,
            is_relevant=is_relevant,
            relevance_reasoning=result.get("relevance_reasoning"),
            context_found=context_found,
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error creating assignment: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(status_code=500, detail=error_msg)

# ============================================================
# STUDENT ENDPOINTS
# ============================================================

@app.post("/submit-assignment", response_model=SubmissionResponse)
async def submit_assignment(
    request: SubmissionRequest,
    user: UserContext = Depends(get_current_user)
):
    """
    Submit an assignment (Student only).
    
    Students can only submit to assignments from their teacher.
    """
    if not user.is_student():
        raise HTTPException(
            status_code=403,
            detail="Only students can submit assignments"
        )
    
    try:
        logger.info(f"Student {user.email} submitting assignment {request.assignment_id}")
        
        # Get user profile for section/roll_number
        profile = get_user_profile(user.user_id)
        roll_number = request.roll_number or profile.get("roll_number") if profile else None
        
        # Section is optional - use from request if provided, otherwise None
        # No longer required in class-based system
        section = None
        if request.section and request.section.strip() and request.section.strip() != "TEMP-PENDING":
            section = request.section.strip()
        
        # Create submission
        submission_id = create_submission_in_db(
            assignment_id=request.assignment_id,
            student_id=user.user_id,
            roll_number=roll_number,
            section=section,
            file_url=request.file_url,
            answer_text=request.answer_text
        )
        
        if not submission_id:
            raise HTTPException(status_code=500, detail="Failed to create submission")
        
        # Log audit trail
        log_submission(
            user_id=user.user_id,
            user_role=user.role,
            submission_id=submission_id,
            assignment_id=request.assignment_id
        )
        
        return SubmissionResponse(
            success=True,
            submission_id=submission_id,
            message="Assignment submitted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting assignment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/unsubmit-assignment")
async def unsubmit_assignment(
    assignment_id: str,
    user: UserContext = Depends(get_current_user)
):
    """
    Unsubmit/delete an assignment submission (Student only).
    
    Students can only unsubmit their own submissions.
    """
    if not user.is_student():
        raise HTTPException(
            status_code=403,
            detail="Only students can unsubmit assignments"
        )
    
    try:
        logger.info(f"Student {user.email} unsubmitting assignment {assignment_id}")
        
        if not db_supabase:
            raise HTTPException(status_code=500, detail="Database not configured")
        
        # Find the submission for this student and assignment
        result = db_supabase.table("submissions").select("id, file_url").eq("student_id", user.user_id).eq("assignment_id", assignment_id).execute()
        
        if not result.data or len(result.data) == 0:
            # Submission doesn't exist - return success (idempotent operation)
            logger.info(f"No submission found for assignment {assignment_id} - already unsubmitted or never submitted")
            return {
                "success": True,
                "message": "Assignment is not submitted (already unsubmitted or never submitted)"
            }
        
        submission = result.data[0]
        submission_id = submission["id"]
        file_url = submission.get("file_url")
        
        # Delete the file from storage if it exists
        if file_url:
            try:
                # Extract file path from URL
                # URL format: https://[project].supabase.co/storage/v1/object/public/assignment-submissions/[filename]
                if "assignment-submissions/" in file_url:
                    file_path = file_url.split("assignment-submissions/")[-1]
                    logger.info(f"Deleting file from storage: {file_path}")
                    delete_result = db_supabase.storage.from_("assignment-submissions").remove([file_path])
                    logger.info(f"File deletion result: {delete_result}")
            except Exception as e:
                logger.warning(f"Could not delete file from storage: {e}")
                # Continue with submission deletion even if file deletion fails
        
        # Delete the submission record
        delete_result = db_supabase.table("submissions").delete().eq("id", submission_id).execute()
        
        if delete_result.data or (hasattr(delete_result, 'data') and delete_result.data is not None):
            logger.info(f"✓ Successfully unsubmitted assignment {assignment_id} for student {user.email}")
            
            # Log audit trail
            log_action(
                user_id=user.user_id,
                user_role=user.role,
                action="unsubmit_assignment",
                resource_type="submission",
                resource_id=submission_id,
                metadata={
                    "assignment_id": assignment_id,
                    "details": f"Unsubmitted assignment {assignment_id}"
                }
            )
            
            return {
                "success": True,
                "message": "Assignment unsubmitted successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to delete submission")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unsubmitting assignment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error unsubmitting assignment: {str(e)}")

# ============================================================
# SHARED ENDPOINTS
# ============================================================

@app.get("/get-my-assignments")
async def get_my_assignments(
    class_id: Optional[str] = None,
    user: UserContext = Depends(get_current_user)
):
    """
    Get assignments visible to the current user.
    
    - Students: See assignments from classes they're enrolled in (or all if class_id not provided)
    - Teachers: See their own assignments (optionally filtered by class_id)
    - Admins: See all assignments
    
    Query parameter:
    - class_id (optional): Filter assignments by class
    """
    try:
        logger.info(f"🔍 Fetching assignments for user: {user.user_id} (role: {user.role})" + (f" (class: {class_id})" if class_id else ""))
        
        # Handle dev mode: if using dev UUID, try to find actual user by email
        actual_user_id = user.user_id
        dev_user_id = "00000000-0000-0000-0000-000000000001"
        if user.user_id == dev_user_id or user.user_id == "dev-user-id":
            logger.info(f"Dev mode detected, looking up actual user by email: {user.email}")
            existing_user = get_user_by_email(user.email)
            if existing_user:
                actual_user_id = existing_user['id']
                logger.info(f"✓ Found actual user ID: {actual_user_id} for dev user {user.email}")
            else:
                logger.warning(f"⚠️ Dev user {user.email} not found in database, using dev UUID")
        
        if user.is_student():
            assignments = get_student_assignments(actual_user_id, class_id)
        elif user.is_teacher():
            assignments = get_teacher_assignments(actual_user_id, class_id)
        elif user.is_admin():
            # Admins see all - would need admin helper function
            assignments = []  # TODO: Implement admin view
        else:
            assignments = []
        
        logger.info(f"✓ Returning {len(assignments)} assignments for user {actual_user_id}")
        
        return {
            "success": True,
            "assignments": assignments,
            "count": len(assignments)
        }
    except Exception as e:
        logger.error(f"Error fetching assignments: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# TEACHER ENDPOINTS (continued)
# ============================================================

@app.get("/get-my-submissions")
async def get_my_submissions(
    assignment_id: Optional[str] = None,
    user: UserContext = Depends(get_current_user)
):
    """
    Get student's own submissions (Student only).
    
    Students can view their own submission details including grades, feedback, and files.
    """
    if not user.is_student():
        raise HTTPException(
            status_code=403,
            detail="Only students can view their own submissions"
        )
    
    try:
        # Handle dev mode: if using dev UUID, try to find actual user by email
        actual_user_id = user.user_id
        dev_user_id = "00000000-0000-0000-0000-000000000001"
        if user.user_id == dev_user_id or user.user_id == "dev-user-id":
            logger.info(f"Dev mode detected in get_my_submissions, looking up actual user by email: {user.email}")
            existing_user = get_user_by_email(user.email)
            if existing_user:
                actual_user_id = existing_user['id']
                logger.info(f"✓ Found actual user ID: {actual_user_id} for dev user {user.email}")
        
        # Get student's submissions
        all_submissions = get_student_submissions(actual_user_id)
        
        # Filter by assignment_id if provided
        if assignment_id:
            all_submissions = [s for s in all_submissions if s.get("assignment_id") == assignment_id]
        
        logger.info(f"✓ Returning {len(all_submissions)} submissions for student {actual_user_id}")
        
        return {
            "success": True,
            "submissions": all_submissions,
            "count": len(all_submissions)
        }
    except Exception as e:
        logger.error(f"Error fetching student submissions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get-submissions")
async def get_submissions(
    assignment_id: Optional[str] = None,
    user: UserContext = Depends(get_current_user)
):
    """
    Get submissions (Teacher only).
    
    Teachers can only see submissions from their students.
    """
    if not user.is_teacher() and not user.is_admin():
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can view submissions"
        )
    
    try:
        # Handle dev mode: if using dev UUID, try to find actual user by email
        actual_user_id = user.user_id
        dev_user_id = "00000000-0000-0000-0000-000000000001"
        if user.user_id == dev_user_id or user.user_id == "dev-user-id":
            logger.info(f"Dev mode detected in get_submissions, looking up actual user by email: {user.email}")
            existing_user = get_user_by_email(user.email)
            if existing_user:
                actual_user_id = existing_user['id']
                logger.info(f"✓ Found actual user ID: {actual_user_id} for dev user {user.email}")
        
        if user.is_teacher():
            submissions = get_teacher_submissions(actual_user_id, assignment_id)
        else:
            # Admin - would need admin helper
            submissions = []
        
        return {
            "success": True,
            "submissions": submissions,
            "count": len(submissions)
        }
    except Exception as e:
        logger.error(f"Error fetching submissions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/grade-assignment")
async def grade_assignment(
    assignment_id: str,
    user: UserContext = Depends(get_current_user)
):
    """
    Grade all submissions for an assignment using AI (Teacher only).
    
    This endpoint:
    1. Fetches all submissions for the assignment
    2. Downloads and parses submission files
    3. Grades each submission using AI with the assignment rubric
    4. Checks for plagiarism
    5. Updates submissions with grades
    """
    logger.info("=" * 80)
    logger.info("🎯 GRADE ASSIGNMENT ENDPOINT CALLED")
    logger.info(f"   Assignment ID: {assignment_id}")
    logger.info(f"   User: {user.email} (ID: {user.user_id}, Role: {user.role})")
    logger.info("=" * 80)
    
    if not user.is_teacher() and not user.is_admin():
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can grade assignments"
        )
    
    try:
        # Handle dev mode: if using dev UUID, try to find actual user by email
        actual_user_id = user.user_id
        dev_user_id = "00000000-0000-0000-0000-000000000001"
        if user.user_id == dev_user_id or user.user_id == "dev-user-id":
            logger.info(f"Dev mode detected in grade_assignment, looking up actual user by email: {user.email}")
            existing_user = get_user_by_email(user.email)
            if existing_user:
                actual_user_id = existing_user['id']
                logger.info(f"✓ Found actual user ID: {actual_user_id} for dev user {user.email}")
        
        # Verify teacher owns this assignment
        teacher_assignments = get_teacher_assignments(actual_user_id)
        assignment_ids = [a["id"] for a in teacher_assignments]
        
        if assignment_id not in assignment_ids:
            raise HTTPException(
                status_code=403,
                detail="You can only grade assignments you created"
            )
        
        logger.info(f"🚀 Starting grading process for assignment {assignment_id}")
        
        # First, check if there are any submissions for this assignment
        submissions_check = get_teacher_submissions(actual_user_id, assignment_id)
        logger.info(f"   Found {len(submissions_check)} submissions via get_teacher_submissions")
        if len(submissions_check) == 0:
            return {
                "success": True,
                "message": "No submissions found for this assignment",
                "graded_count": 0,
                "failed_count": 0,
                "assignment_id": assignment_id
            }
        
        # Get student IDs for this teacher (to filter submissions)
        students = get_teacher_students(actual_user_id)
        student_ids = [s["id"] for s in students]
        logger.info(f"   Teacher has {len(student_ids)} linked students - will only grade their submissions")
        
        # Invoke the grading graph
        grading_input = {
            "assignment_id": assignment_id,
            "submission_ids": [],
            "student_ids": student_ids  # Pass student IDs to filter submissions
        }
        
        logger.info(f"   Invoking grading graph with assignment_id: {assignment_id}, student_ids: {len(student_ids)} students")
        result = assignment_grader_graph.invoke(grading_input)
        
        logger.info(f"✓ Grading graph completed for assignment {assignment_id}")
        logger.info(f"   Result keys: {list(result.keys()) if result else 'None'}")
        logger.info(f"   Result type: {type(result)}")
        
        # Debug: Print full result structure
        import json
        try:
            result_str = json.dumps(result, default=str, indent=2)
            logger.info(f"   Full result (first 1000 chars): {result_str[:1000]}")
        except:
            logger.info(f"   Could not serialize result for logging")
        
        # Update submissions in database with grades
        graded_count = 0
        failed_count = 0
        
        if result and "submission_ids" in result:
            submissions_list = result["submission_ids"]
            logger.info(f"   Found {len(submissions_list)} submissions in result")
            
            if len(submissions_list) == 0:
                logger.warning(f"   ⚠️ No submissions in result - check if submissions were found and graded")
            
            for i, submission in enumerate(submissions_list):
                logger.info(f"   Processing submission {i+1}/{len(submissions_list)}")
                logger.info(f"   Submission type: {type(submission)}")
                logger.info(f"   Submission repr: {repr(submission)[:200]}")
                
                # Handle both Pydantic model and dict formats
                if hasattr(submission, 'submission_id'):
                    submission_id = submission.submission_id
                    total_score_obj = submission.total_score
                    plagiarism = submission.plagerism_score
                    web_sources = submission.web_sources if hasattr(submission, 'web_sources') else None
                    academic_sources = submission.academic_sources if hasattr(submission, 'academic_sources') else None
                elif isinstance(submission, dict):
                    submission_id = submission.get('submission_id') or submission.get('id')
                    total_score_obj = submission.get('total_score')
                    plagiarism = submission.get('plagerism_score')
                    web_sources = submission.get('web_sources')
                    academic_sources = submission.get('academic_sources')
                else:
                    logger.error(f"   Unknown submission format: {type(submission)}")
                    failed_count += 1
                    continue
                
                # Convert Pydantic models to dicts for database storage
                if web_sources and isinstance(web_sources, list):
                    web_sources = [s.dict() if hasattr(s, 'dict') else s for s in web_sources]
                if academic_sources and isinstance(academic_sources, list):
                    academic_sources = [s.dict() if hasattr(s, 'dict') else s for s in academic_sources]
                
                logger.info(f"   Submission ID: {submission_id}")
                logger.info(f"   Plagiarism score: {plagiarism}")
                logger.info(f"   Total score object type: {type(total_score_obj)}")
                logger.info(f"   Total score object: {total_score_obj}")
                
                if total_score_obj:
                    # Handle both Pydantic model and dict formats for total_score
                    if hasattr(total_score_obj, 'total_score'):
                        grade = total_score_obj.total_score
                        reason = total_score_obj.reason
                    elif isinstance(total_score_obj, dict):
                        grade = total_score_obj.get('total_score')
                        reason = total_score_obj.get('reason')
                    else:
                        logger.warning(f"   Unknown total_score format: {type(total_score_obj)}, value: {total_score_obj}")
                        failed_count += 1
                        continue
                    
                    # Validate grade and reason
                    if grade is None:
                        logger.warning(f"   Grade is None for submission {submission_id}")
                        failed_count += 1
                        continue
                    if not reason:
                        logger.warning(f"   Reason is empty for submission {submission_id}")
                        reason = "No reason provided"
                    
                    # CRITICAL: Check if grade should be 0 due to plagiarism (double-check)
                    PLAGIARISM_THRESHOLD = 40.0
                    logger.info(f"   Checking plagiarism: {plagiarism}% vs threshold {PLAGIARISM_THRESHOLD}%")
                    logger.info(f"   Current grade before plagiarism check: {grade}")
                    
                    if plagiarism is not None and plagiarism > PLAGIARISM_THRESHOLD:
                        logger.warning(f"   ⚠️ Plagiarism {plagiarism}% > threshold {PLAGIARISM_THRESHOLD}% - grade should be 0, but got {grade}")
                        if grade != 0.0:
                            logger.error(f"   ❌ ERROR: Grade is {grade} but should be 0 due to plagiarism! FORCING TO 0...")
                            # Force grade to 0
                            grade = 0.0
                            reason = f"Grade set to 0 due to high plagiarism score ({plagiarism}% similarity, threshold: {PLAGIARISM_THRESHOLD}%). " + reason
                            logger.info(f"   ✓ Grade forced to 0")
                        else:
                            logger.info(f"   ✓ Grade is already 0 (correct)")
                    else:
                        logger.info(f"   ✓ Plagiarism {plagiarism}% is acceptable (<= {PLAGIARISM_THRESHOLD}%)")
                    
                    logger.info(f"   Final Grade to save: {grade}, Reason length: {len(reason) if reason else 0}")
                    
                    success = update_submission_grade(
                        submission_id=submission_id,
                        grade=grade,
                        grade_reason=reason,
                        plagiarism_score=plagiarism,
                        web_sources=web_sources,
                        academic_sources=academic_sources
                    )
                    
                    if success:
                        graded_count += 1
                        logger.info(f"   ✓ Successfully updated grade for submission {submission_id}")
                    else:
                        failed_count += 1
                        logger.warning(f"   ✗ Failed to update grade for submission {submission_id}")
                else:
                    # No grade was assigned - this usually means an error occurred during grading
                    logger.warning(f"   ⚠️ Submission {submission_id} has no grade (total_score_obj is None)")
                    logger.warning(f"   This usually means:")
                    logger.warning(f"   1. The LLM API hit a rate limit (check logs for 429 errors)")
                    logger.warning(f"   2. An error occurred during grading (check logs above)")
                    logger.warning(f"   3. The grading process was interrupted")
                    failed_count += 1
                    continue
        else:
            logger.warning(f"   No submissions in result or result structure is invalid")
            if result:
                logger.warning(f"   Result keys: {list(result.keys())}")
        
        logger.info(f"✓ Grading complete: {graded_count} graded, {failed_count} failed")
        
        return {
            "success": True,
            "message": f"Graded {graded_count} submission(s) successfully",
            "graded_count": graded_count,
            "failed_count": failed_count,
            "assignment_id": assignment_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error grading assignment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error grading assignment: {str(e)}")

@app.get("/export-grades-csv")
async def export_grades_csv(
    assignment_id: str,
    user: UserContext = Depends(get_current_user)
):
    """
    Export grades for an assignment as CSV (Teacher only).
    
    Returns a CSV file with all submission grades including:
    - Student information (name, roll number, section)
    - Assignment details
    - Grade, plagiarism score, grade reason
    - Submission date
    """
    if not user.is_teacher() and not user.is_admin():
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can export grades"
        )
    
    try:
        logger.info(f"📊 Exporting grades CSV for assignment {assignment_id} by {user.email}")
        
        # Initialize actual_user_id (used for both ownership check and fetching submissions)
        actual_user_id = user.user_id
        
        # Verify assignment belongs to teacher (unless admin)
        if not user.is_admin():
            # Handle dev mode: if using dev UUID, try to find actual user by email
            dev_user_id = "00000000-0000-0000-0000-000000000001"
            is_dev_mode = user.user_id == dev_user_id or user.user_id == "dev-user-id"
            
            if is_dev_mode:
                logger.info(f"Dev mode detected in export_grades_csv, looking up actual user by email: {user.email}")
                existing_user = get_user_by_email(user.email)
                if existing_user:
                    actual_user_id = existing_user['id']
                    logger.info(f"✓ Found actual user ID: {actual_user_id} for dev user {user.email}")
            
            # Directly verify assignment ownership by querying the assignment
            try:
                if db_supabase:
                    result = db_supabase.table("assignments").select("teacher_id").eq("id", assignment_id).execute()
                    if not result.data:
                        logger.warning(f"   Assignment {assignment_id} not found in database")
                        raise HTTPException(
                            status_code=404,
                            detail=f"Assignment {assignment_id} not found"
                        )
                    
                    assignment_teacher_id = result.data[0].get("teacher_id")
                    logger.info(f"   Assignment {assignment_id} belongs to teacher: {assignment_teacher_id}")
                    logger.info(f"   Current user ID: {actual_user_id}")
                    
                    # In dev mode, if the user lookup failed (wrong email), try to use the assignment's teacher_id
                    if is_dev_mode and str(assignment_teacher_id) != str(actual_user_id):
                        logger.info(f"   Dev mode: assignment teacher ID doesn't match, checking if we can use assignment's teacher_id")
                        # Check if the assignment's teacher can access submissions (class-based access check)
                        # This handles the case where token decoding failed but the user should have access
                        try:
                            test_submissions = get_teacher_submissions(assignment_teacher_id, assignment_id)
                            if test_submissions:
                                logger.info(f"   Dev mode: Assignment teacher {assignment_teacher_id} can access submissions, allowing export")
                                actual_user_id = assignment_teacher_id
                            else:
                                logger.warning(f"   Dev mode: Assignment teacher {assignment_teacher_id} cannot access submissions")
                        except Exception as e:
                            logger.warning(f"   Dev mode: Error checking submissions access: {e}")
                    
                    if str(assignment_teacher_id) != str(actual_user_id):
                        logger.warning(f"   Assignment ownership mismatch: assignment belongs to {assignment_teacher_id}, but user is {actual_user_id}")
                        raise HTTPException(
                            status_code=403,
                            detail="You can only export grades for your own assignments"
                        )
                    logger.info(f"   ✓ Assignment ownership verified")
                else:
                    # Fallback to list-based check if supabase not available
                    assignments = get_teacher_assignments(actual_user_id)
                    assignment_ids = [a.get("id") for a in assignments]
                    if assignment_id not in assignment_ids:
                        logger.warning(f"   Assignment {assignment_id} not found in teacher's assignments")
                        raise HTTPException(
                            status_code=403,
                            detail="You can only export grades for your own assignments"
                        )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"   Error verifying assignment ownership: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail="Error verifying assignment ownership"
                )
        
        # Get all submissions for this assignment
        # Use the same actual_user_id we determined during ownership check
        # (it's already set above, but we ensure it's used consistently)
        submissions = get_teacher_submissions(actual_user_id, assignment_id)
        
        if not submissions:
            raise HTTPException(
                status_code=404,
                detail="No submissions found for this assignment"
            )
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "Student Name",
            "Roll Number",
            "Assignment Title",
            "Grade",
            "Plagiarism Score (%)",
            "Grade Reason",
            "Submission Date",
            "File URL"
        ])
        
        # Write data rows
        for submission in submissions:
            profile = submission.get("profiles", {})
            assignment = submission.get("assignments", {})
            
            student_name = profile.get("name", "N/A") if profile else "N/A"
            roll_number = submission.get("roll_number") or profile.get("roll_number", "N/A") if profile else "N/A"
            assignment_title = assignment.get("topic", assignment.get("title", "N/A")) if assignment else "N/A"
            grade = submission.get("grade", "Not Graded")
            plagiarism_score = submission.get("plagiarism_score", "N/A")
            grade_reason = submission.get("grade_reason", "N/A") or "N/A"
            submission_date = submission.get("submitted_at", "N/A")
            file_url = submission.get("file_url", "N/A") or "N/A"
            
            # Format date if available
            if submission_date and submission_date != "N/A":
                try:
                    if isinstance(submission_date, str):
                        # Parse ISO format date
                        dt = datetime.fromisoformat(submission_date.replace('Z', '+00:00'))
                        submission_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass  # Keep original if parsing fails
            
            writer.writerow([
                student_name,
                roll_number,
                assignment_title,
                grade,
                plagiarism_score,
                grade_reason[:200] if grade_reason and len(grade_reason) > 200 else grade_reason,  # Truncate long reasons
                submission_date,
                file_url
            ])
        
        # Get CSV content
        csv_content = output.getvalue()
        output.close()
        
        # Generate filename with assignment title and date
        # Get assignment title from first submission (all submissions have same assignment)
        assignment_title = "assignment"
        if submissions and len(submissions) > 0:
            first_submission = submissions[0]
            assignment_data = first_submission.get("assignments", {})
            if assignment_data:
                assignment_title = assignment_data.get("title", "assignment")
        
        assignment_title_safe = assignment_title[:50] if assignment_title else "assignment"
        assignment_title_safe = "".join(c for c in assignment_title_safe if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"grades_{assignment_title_safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        logger.info(f"✓ Generated CSV with {len(submissions)} submissions")
        
        # Return CSV as downloadable file
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting grades CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error exporting grades: {str(e)}")

# ============================================================
# ASSIGNMENT MANAGEMENT ENDPOINTS
# ============================================================

@app.put("/update-assignment")
async def update_assignment(
    assignment_id: str,
    request: AssignmentRequest,
    user: UserContext = Depends(get_current_user)
):
    """
    Update an assignment (Teacher only).
    
    Teachers can only update their own assignments.
    """
    if not user.is_teacher() and not user.is_admin():
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can update assignments"
        )
    
    try:
        # Handle dev mode: resolve actual user ID
        actual_user_id = user.user_id
        dev_user_id = "00000000-0000-0000-0000-000000000001"
        if user.user_id == dev_user_id or user.user_id == "dev-user-id":
            existing_user = get_user_by_email(user.email)
            if existing_user:
                actual_user_id = existing_user['id']
        
        logger.info(f"Teacher {user.email} updating assignment {assignment_id}")
        
        # Update assignment in database
        success = update_assignment_in_db(
            assignment_id=assignment_id,
            teacher_id=actual_user_id,
            topic=request.topic,
            description=request.description,
            assignment_type=request.type,
            num_questions=request.num_questions,
            deadline=request.deadline,
            published=request.published if request.published is not None else None
        )
        
        if success:
            return {
                "success": True,
                "message": "Assignment updated successfully"
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to update assignment. Make sure you own this assignment."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating assignment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/delete-assignment")
async def delete_assignment(
    assignment_id: str,
    user: UserContext = Depends(get_current_user)
):
    """
    Delete an assignment (Teacher only).
    
    Teachers can only delete their own assignments.
    """
    if not user.is_teacher() and not user.is_admin():
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can delete assignments"
        )
    
    try:
        # Handle dev mode: resolve actual user ID
        actual_user_id = user.user_id
        dev_user_id = "00000000-0000-0000-0000-000000000001"
        if user.user_id == dev_user_id or user.user_id == "dev-user-id":
            existing_user = get_user_by_email(user.email)
            if existing_user:
                actual_user_id = existing_user['id']
        
        logger.info(f"Teacher {user.email} deleting assignment {assignment_id}")
        
        # Delete assignment from database
        success = delete_assignment_in_db(
            assignment_id=assignment_id,
            teacher_id=actual_user_id
        )
        
        if success:
            return {
                "success": True,
                "message": "Assignment deleted successfully"
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to delete assignment. Make sure you own this assignment."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting assignment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# CLASS MANAGEMENT ENDPOINTS
# ============================================================

@app.post("/create-class")
async def create_class_endpoint(
    request: ClassRequest,
    user: UserContext = Depends(get_current_user)
):
    """
    Create a new class (Teacher/Admin only).
    """
    if not user.is_teacher() and not user.is_admin():
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can create classes"
        )
    
    try:
        # Handle dev mode
        actual_user_id = user.user_id
        dev_user_id = "00000000-0000-0000-0000-000000000001"
        if user.user_id == dev_user_id or user.user_id == "dev-user-id":
            existing_user = get_user_by_email(user.email)
            if existing_user:
                actual_user_id = existing_user['id']
        
        logger.info(f"User {user.email} creating class: {request.name}")
        
        class_id = create_class(request.name, request.code, request.description)
        
        if class_id:
            # Automatically assign the teacher to the class
            assign_teacher_to_class(actual_user_id, class_id)
            
            return {
                "success": True,
                "class_id": class_id,
                "message": "Class created successfully"
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create class"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating class: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get-my-classes")
async def get_my_classes(
    user: UserContext = Depends(get_current_user)
):
    """
    Get classes for the current user.
    
    - Students: Get classes they're enrolled in
    - Teachers: Get classes they teach
    - Admins: Get all classes (TODO)
    """
    try:
        # Handle dev mode
        actual_user_id = user.user_id
        dev_user_id = "00000000-0000-0000-0000-000000000001"
        if user.user_id == dev_user_id or user.user_id == "dev-user-id":
            existing_user = get_user_by_email(user.email)
            if existing_user:
                actual_user_id = existing_user['id']
        
        if user.is_student():
            classes = get_student_classes(actual_user_id)
        elif user.is_teacher():
            classes = get_teacher_classes(actual_user_id)
        elif user.is_admin():
            classes = []  # TODO: Implement admin view
        else:
            classes = []
        
        return {
            "success": True,
            "classes": classes,
            "count": len(classes)
        }
    except Exception as e:
        logger.error(f"Error fetching classes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/enroll-student")
async def enroll_student_endpoint(
    student_id: str,
    class_id: str,
    user: UserContext = Depends(get_current_user)
):
    """
    Enroll a student in a class (Teacher/Admin only).
    
    Teachers can only enroll students in classes they teach.
    """
    if not user.is_teacher() and not user.is_admin():
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can enroll students"
        )
    
    try:
        # Handle dev mode
        actual_user_id = user.user_id
        dev_user_id = "00000000-0000-0000-0000-000000000001"
        if user.user_id == dev_user_id or user.user_id == "dev-user-id":
            existing_user = get_user_by_email(user.email)
            if existing_user:
                actual_user_id = existing_user['id']
        
        # Verify teacher teaches this class (unless admin)
        if not user.is_admin():
            teacher_classes = get_teacher_classes(actual_user_id)
            class_ids = [c["id"] for c in teacher_classes]
            if class_id not in class_ids:
                raise HTTPException(
                    status_code=403,
                    detail="You can only enroll students in classes you teach"
                )
        
        success = enroll_student_in_class(student_id, class_id)
        
        if success:
            return {
                "success": True,
                "message": "Student enrolled successfully"
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to enroll student"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enrolling student: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get-class-students")
async def get_class_students_endpoint(
    class_id: str,
    user: UserContext = Depends(get_current_user)
):
    """
    Get all students enrolled in a class (Teacher/Admin only).
    
    Teachers can only view students in classes they teach.
    """
    if not user.is_teacher() and not user.is_admin():
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can view class students"
        )
    
    try:
        # Handle dev mode
        actual_user_id = user.user_id
        dev_user_id = "00000000-0000-0000-0000-000000000001"
        if user.user_id == dev_user_id or user.user_id == "dev-user-id":
            existing_user = get_user_by_email(user.email)
            if existing_user:
                actual_user_id = existing_user['id']
        
        # Verify teacher teaches this class (unless admin)
        if not user.is_admin():
            teacher_classes = get_teacher_classes(actual_user_id)
            class_ids = [c["id"] for c in teacher_classes]
            if class_id not in class_ids:
                raise HTTPException(
                    status_code=403,
                    detail="You can only view students in classes you teach"
                )
        
        students = get_class_students(class_id)
        
        return {
            "success": True,
            "students": students,
            "count": len(students)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching class students: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/enroll-by-code")
async def enroll_by_code_endpoint(
    class_code: str,
    user: UserContext = Depends(get_current_user)
):
    """
    Enroll a student in a class using the class code (Student only).
    
    Students can enroll themselves in any class by providing the class code.
    """
    if not user.is_student():
        raise HTTPException(
            status_code=403,
            detail="Only students can enroll themselves in classes"
        )
    
    try:
        # Handle dev mode
        actual_user_id = user.user_id
        dev_user_id = "00000000-0000-0000-0000-000000000001"
        if user.user_id == dev_user_id or user.user_id == "dev-user-id":
            existing_user = get_user_by_email(user.email)
            if existing_user:
                actual_user_id = existing_user['id']
        
        logger.info(f"Student {user.email} attempting to enroll in class with code: {class_code}")
        
        # Find class by code
        class_data = get_class_by_code(class_code)
        if not class_data:
            raise HTTPException(
                status_code=404,
                detail=f"Class with code '{class_code}' not found"
            )
        
        class_id = class_data["id"]
        
        # Check if already enrolled
        if is_student_enrolled(actual_user_id, class_id):
            raise HTTPException(
                status_code=400,
                detail=f"You are already enrolled in {class_data.get('name', 'this class')}"
            )
        
        # Enroll the student
        success = enroll_student_in_class(actual_user_id, class_id)
        
        if success:
            logger.info(f"✓ Student {user.email} enrolled in class {class_data.get('name')} ({class_code})")
            return {
                "success": True,
                "message": f"Successfully enrolled in {class_data.get('name', 'class')}",
                "class": {
                    "id": class_id,
                    "name": class_data.get("name"),
                    "code": class_data.get("code")
                }
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to enroll in class"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enrolling student by code: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# ADMIN ENDPOINTS
# ============================================================

@app.get("/admin/stats")
async def admin_stats(
    user: UserContext = Depends(get_current_user)
):
    """Get system statistics (Admin only)."""
    if not user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        stats = get_system_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error fetching admin stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/users")
async def admin_get_users(
    role: Optional[str] = None,
    user: UserContext = Depends(get_current_user)
):
    """Get all users (Admin only). Optionally filter by role."""
    if not user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        users = get_all_users(role=role)
        return {
            "success": True,
            "users": users
        }
    except Exception as e:
        logger.error(f"Error fetching users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/classes")
async def admin_get_classes(
    user: UserContext = Depends(get_current_user)
):
    """Get all classes (Admin only)."""
    if not user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        classes = get_all_classes()
        return {
            "success": True,
            "classes": classes
        }
    except Exception as e:
        logger.error(f"Error fetching classes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/assignments")
async def admin_get_assignments(
    user: UserContext = Depends(get_current_user)
):
    """Get all assignments (Admin only)."""
    if not user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        assignments = get_all_assignments()
        return {
            "success": True,
            "assignments": assignments
        }
    except Exception as e:
        logger.error(f"Error fetching assignments: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/admin/users/{user_id}/role")
async def admin_update_user_role(
    user_id: str,
    new_role: str = Query(..., description="New role: 'admin', 'teacher', or 'student'"),
    admin_user: UserContext = Depends(get_current_user)
):
    """Update user role (Admin only)."""
    if not admin_user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    
    if new_role not in ["admin", "teacher", "student"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin', 'teacher', or 'student'")
    
    try:
        success = update_user_role(user_id, new_role)
        if success:
            return {
                "success": True,
                "message": f"User role updated to {new_role}"
            }
        else:
            raise HTTPException(status_code=404, detail="User not found or update failed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user role: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/classes/{class_id}/teachers/{teacher_id}")
async def admin_assign_teacher(
    class_id: str,
    teacher_id: str,
    admin_user: UserContext = Depends(get_current_user)
):
    """Assign a teacher to a class (Admin only)."""
    if not admin_user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        success = assign_teacher_to_class_admin(class_id, teacher_id)
        if success:
            return {
                "success": True,
                "message": "Teacher assigned to class"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to assign teacher to class")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning teacher: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/classes/{class_id}/students/{student_id}")
async def admin_enroll_student(
    class_id: str,
    student_id: str,
    admin_user: UserContext = Depends(get_current_user)
):
    """Enroll a student in a class (Admin only)."""
    if not admin_user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        success = enroll_student_in_class_admin(class_id, student_id)
        if success:
            return {
                "success": True,
                "message": "Student enrolled in class"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to enroll student in class")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enrolling student: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/admin/classes/{class_id}/users/{user_id}")
async def admin_remove_user_from_class(
    class_id: str,
    user_id: str,
    user_role: str = Query(..., description="Role of user to remove: 'teacher' or 'student'"),
    admin_user: UserContext = Depends(get_current_user)
):
    """Remove a user (teacher or student) from a class (Admin only)."""
    if not admin_user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    
    if user_role not in ["teacher", "student"]:
        raise HTTPException(status_code=400, detail="Invalid user_role. Must be 'teacher' or 'student'")
    
    try:
        success = remove_user_from_class(user_id, class_id, user_role)
        if success:
            return {
                "success": True,
                "message": f"{user_role.capitalize()} removed from class"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to remove user from class")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing user from class: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/admin/users/{user_id}")
async def admin_delete_user(
    user_id: str,
    admin_user: UserContext = Depends(get_current_user)
):
    """Delete a user (Admin only)."""
    if not admin_user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Prevent self-deletion
    if user_id == admin_user.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    try:
        success = delete_user_profile(user_id)
        if success:
            return {
                "success": True,
                "message": "User deleted successfully"
            }
        else:
            raise HTTPException(status_code=404, detail="User not found or deletion failed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/admin/classes/{class_id}")
async def admin_update_class(
    class_id: str,
    name: Optional[str] = None,
    code: Optional[str] = None,
    description: Optional[str] = None,
    admin_user: UserContext = Depends(get_current_user)
):
    """Update a class (Admin only)."""
    if not admin_user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        update_data = {}
        if name is not None:
            update_data["name"] = name
        if code is not None:
            update_data["code"] = code
        if description is not None:
            update_data["description"] = description
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        if not db_supabase:
            raise HTTPException(status_code=500, detail="Database not available")
        
        result = db_supabase.table("classes").update(update_data).eq("id", class_id).execute()
        
        if result.data and len(result.data) > 0:
            return {
                "success": True,
                "message": "Class updated successfully",
                "class": result.data[0]
            }
        else:
            raise HTTPException(status_code=404, detail="Class not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating class: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/admin/classes/{class_id}")
async def admin_delete_class(
    class_id: str,
    admin_user: UserContext = Depends(get_current_user)
):
    """Delete a class (Admin only)."""
    if not admin_user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        if not db_supabase:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Delete class (cascade should handle related records)
        result = db_supabase.table("classes").delete().eq("id", class_id).execute()
        
        return {
            "success": True,
            "message": "Class deleted successfully"
        }
    except Exception as e:
        logger.error(f"Error deleting class: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# ANALYTICS ENDPOINTS (Teacher only)
# ============================================================

@app.get("/analytics")
async def get_analytics(
    assignment_id: Optional[str] = None,
    class_id: Optional[str] = None,
    user: UserContext = Depends(get_current_user)
):
    """
    Get analytics for teacher's assignments.
    
    Returns submission rates, average grades, and late submission percentages.
    Can be filtered by assignment_id or class_id.
    """
    if not user.is_teacher() and not user.is_admin():
        raise HTTPException(
            status_code=403,
            detail="Only teachers and admins can view analytics"
        )
    
    try:
        # Handle dev mode
        actual_user_id = user.user_id
        dev_user_id = "00000000-0000-0000-0000-000000000001"
        if user.user_id == dev_user_id or user.user_id == "dev-user-id":
            existing_user = get_user_by_email(user.email)
            if existing_user:
                actual_user_id = existing_user['id']
        
        if assignment_id:
            analytics = get_assignment_analytics(actual_user_id, assignment_id=assignment_id, class_id=class_id)
        else:
            analytics = get_overall_analytics(actual_user_id, class_id=class_id)
        
        return {
            "success": True,
            **analytics
        }
    except Exception as e:
        logger.error(f"Error fetching analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# ERROR HANDLERS
# ============================================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"success": False, "error": "Endpoint not found"}
    )

@app.exception_handler(422)
async def validation_error_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={"success": False, "error": "Validation error", "details": str(exc)}
    )

if __name__ == "__main__":
    logger.info("Starting TeachMate Assignment Creator API (RBAC)...")
    uvicorn.run(
        "main_rbac:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

