"""
Database Helper Functions for TeachMate

Provides helper functions for:
- Role checking
- Data filtering based on user role
- Teacher-student relationships
- Section-based queries
"""

import logging
from typing import List, Dict, Any, Optional
from supabase import Client
import os

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, skip

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("✓ Supabase client initialized for DB helpers")
        logger.info(f"   URL: {SUPABASE_URL}")
        logger.info(f"   Service Key: {'*' * 20}...{SUPABASE_SERVICE_KEY[-4:] if len(SUPABASE_SERVICE_KEY) > 4 else '****'}")
    except Exception as e:
        logger.error(f"❌ Could not initialize Supabase client: {e}")
        logger.error(f"   SUPABASE_URL: {SUPABASE_URL}")
        logger.error(f"   SUPABASE_SERVICE_KEY length: {len(SUPABASE_SERVICE_KEY) if SUPABASE_SERVICE_KEY else 0}")
else:
    logger.warning("⚠ Supabase not configured - SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
    logger.warning(f"   SUPABASE_URL: {'SET' if SUPABASE_URL else 'NOT SET'}")
    logger.warning(f"   SUPABASE_SERVICE_KEY: {'SET' if SUPABASE_SERVICE_KEY else 'NOT SET'}")


def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user profile by ID."""
    if not supabase:
        return None
    
    try:
        result = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
        return result.data if result.data else None
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        return None


def get_teacher_students(teacher_id: str) -> List[Dict[str, Any]]:
    """Get all students enrolled in classes taught by a teacher (class-based linking).
    
    This function gets students through classes, not through direct teacher_id links.
    Flow: Teacher → Classes → Students
    """
    if not supabase:
        return []
    
    try:
        # Step 1: Get all classes taught by this teacher
        teacher_classes_result = supabase.table("teacher_class").select("class_id").eq("teacher_id", teacher_id).execute()
        class_ids = [tc["class_id"] for tc in (teacher_classes_result.data or [])]
        
        if not class_ids:
            logger.info(f"Teacher {teacher_id} teaches no classes, no students to return")
            return []
        
        logger.info(f"Teacher {teacher_id} teaches {len(class_ids)} classes")
        
        # Step 2: Get all students enrolled in these classes
        enrollments_result = supabase.table("student_class").select("student_id").in_("class_id", class_ids).execute()
        student_ids = list(set([e["student_id"] for e in (enrollments_result.data or [])]))  # Remove duplicates
        
        if not student_ids:
            logger.info(f"No students enrolled in teacher {teacher_id}'s classes")
            return []
        
        logger.info(f"Found {len(student_ids)} unique students in teacher {teacher_id}'s classes")
        
        # Step 3: Get full student profiles
        students_result = supabase.table("profiles").select("*").in_("id", student_ids).eq("role", "student").execute()
        students = students_result.data if students_result.data else []
        
        logger.info(f"✓ Retrieved {len(students)} student profiles for teacher {teacher_id}")
        return students
    except Exception as e:
        logger.error(f"Error fetching teacher students: {e}", exc_info=True)
        return []


def get_student_assignments(student_id: str, class_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get assignments visible to a student (class-based only).
    
    Students can only see published assignments from classes they're enrolled in.
    This uses class-based linking only - no direct teacher-student links.
    
    If class_id is provided, only returns assignments for that class.
    Each assignment includes an `is_submitted` field indicating if the student has submitted it.
    """
    if not supabase:
        return []
    
    try:
        # Get student profile
        student = get_user_profile(student_id)
        if not student:
            logger.warning(f"Student profile not found for ID: {student_id}")
            return []
        
        assignments = []
        
        # Class-based assignment fetching (ONLY method)
        if class_id:
            # Verify student is enrolled in this class
            if not is_student_enrolled(student_id, class_id):
                logger.warning(f"Student {student_id} is not enrolled in class {class_id}")
                return []
            
            # Get published assignments for this specific class
            logger.info(f"Student {student_id} fetching assignments for class {class_id}")
            result = supabase.table("assignments").select("*").eq("class_id", class_id).eq("published", True).order("created_at", desc=True).execute()
            
            if result.data:
                logger.info(f"✓ Found {len(result.data)} published assignments for class {class_id}")
                assignments = result.data
            else:
                logger.info(f"No published assignments found for class {class_id}")
                return []
        else:
            # Get all classes the student is enrolled in
            student_classes = get_student_classes(student_id)
            class_ids = [c["id"] for c in student_classes]
            
            if not class_ids:
                logger.info(f"Student {student_id} is not enrolled in any classes")
                return []
            
                logger.info(f"Student {student_id} is enrolled in {len(class_ids)} classes, fetching assignments")
                result = supabase.table("assignments").select("*").in_("class_id", class_ids).eq("published", True).order("created_at", desc=True).execute()
                
                if result.data:
                    logger.info(f"✓ Found {len(result.data)} published assignments from enrolled classes")
                    assignments = result.data
                else:
                    logger.info(f"No published assignments found from enrolled classes")
                return []
        
        # Now check submission status for each assignment
        if assignments:
            # Get all submission IDs for this student
            submission_result = supabase.table("submissions").select("assignment_id").eq("student_id", student_id).execute()
            submitted_assignment_ids = set()
            if submission_result.data:
                submitted_assignment_ids = {s["assignment_id"] for s in submission_result.data}
                logger.info(f"✓ Found {len(submitted_assignment_ids)} submitted assignments for student {student_id}")
            
            # Add is_submitted field to each assignment
            # Also map due_date to deadline for frontend consistency
            for assignment in assignments:
                assignment["is_submitted"] = assignment["id"] in submitted_assignment_ids
                # Map due_date to deadline for frontend
                if "due_date" in assignment:
                    assignment["deadline"] = assignment["due_date"]
        
        return assignments
    except Exception as e:
        logger.error(f"Error fetching student assignments: {e}", exc_info=True)
        return []


def get_teacher_assignments(teacher_id: str, class_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all assignments created by a teacher.
    
    If class_id is provided, only returns assignments for that class.
    """
    if not supabase:
        logger.warning("Supabase not configured, cannot fetch assignments")
        return []
    
    try:
        logger.info(f"🔍 Fetching assignments for teacher: {teacher_id}" + (f" (class: {class_id})" if class_id else ""))
        
        query = supabase.table("assignments").select("*").eq("teacher_id", teacher_id)
        if class_id:
            query = query.eq("class_id", class_id)
        
        result = query.order("created_at", desc=True).execute()
        
        if result.data:
            logger.info(f"✓ Found {len(result.data)} assignments for teacher {teacher_id}")
            # Map due_date to deadline for frontend consistency
            for assignment in result.data:
                if "due_date" in assignment:
                    assignment["deadline"] = assignment["due_date"]
            return result.data
        else:
            logger.info(f"✓ No assignments found for teacher {teacher_id}")
            return []
    except Exception as e:
        logger.error(f"❌ Error fetching teacher assignments: {e}", exc_info=True)
        return []


def get_teacher_submissions(teacher_id: str, assignment_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get submissions from students enrolled in classes taught by this teacher (class-based).
    
    Flow: Teacher → Classes → Students → Submissions
    Only returns submissions for assignments created by this teacher.
    """
    if not supabase:
        return []
    
    try:
        logger.info(f"🔍 Fetching submissions for teacher {teacher_id} (class-based)")
        
        # Get all student IDs enrolled in teacher's classes
        students = get_teacher_students(teacher_id)
        student_ids = [s["id"] for s in students]
        
        logger.info(f"   Found {len(student_ids)} students in teacher's classes")
        
        if not student_ids:
            logger.info(f"   No students in teacher {teacher_id}'s classes, returning empty list")
            return []
        
        # Get assignments created by this teacher (to ensure we only show submissions to teacher's assignments)
        assignments_result = supabase.table("assignments").select("id").eq("teacher_id", teacher_id).execute()
        teacher_assignment_ids = [a["id"] for a in (assignments_result.data or [])]
        
        if not teacher_assignment_ids:
            logger.info(f"   Teacher {teacher_id} has no assignments, no submissions to show")
            return []
        
        logger.info(f"   Teacher has {len(teacher_assignment_ids)} assignments")
        
        # Build query: submissions from students in teacher's classes AND for teacher's assignments
        query = supabase.table("submissions").select("*, assignments(*), profiles(*)")
        
        # Filter by student IDs (only students enrolled in teacher's classes)
        query = query.in_("student_id", student_ids)
        
        # Filter by assignment IDs (only assignments created by this teacher)
        query = query.in_("assignment_id", teacher_assignment_ids)
        
        # If specific assignment requested, add that filter too
        if assignment_id:
            if assignment_id in teacher_assignment_ids:
                query = query.eq("assignment_id", assignment_id)
            else:
                logger.warning(f"Assignment {assignment_id} not found for teacher {teacher_id}")
                return []
        
        result = query.execute()
        submissions = result.data if result.data else []
        
        logger.info(f"✓ Found {len(submissions)} submissions from students in teacher's classes")
        return submissions
    except Exception as e:
        logger.error(f"❌ Error fetching teacher submissions: {e}", exc_info=True)
        return []


def get_student_submissions(student_id: str) -> List[Dict[str, Any]]:
    """Get all submissions by a student."""
    if not supabase:
        return []
    
    try:
        result = supabase.table("submissions").select("*, assignments(*)").eq("student_id", student_id).execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error fetching student submissions: {e}")
        return []


def create_assignment_in_db(
    teacher_id: str,
    section: Optional[str],
    topic: str,
    description: str,
    assignment_type: str,
    num_questions: int,
    questions: List[Dict[str, Any]],
    rubric: Dict[str, Any],
    published: bool = False,
    deadline: Optional[str] = None,
    class_id: Optional[str] = None
) -> Optional[str]:
    """Create assignment in database and return assignment ID."""
    if not supabase:
        logger.error("❌ Supabase not configured, cannot save assignment")
        return None
    
    try:
        assignment_data = {
            "teacher_id": teacher_id,
            "section": section if section else "",  # Database requires non-null, use empty string if None
            "topic": topic,
            "description": description,
            "type": assignment_type,
            "num_questions": num_questions,
            "questions": questions,
            "rubric": rubric,
            "published": published
        }
        
        # Add deadline if provided (map to due_date in database)
        if deadline:
            assignment_data["due_date"] = deadline
        
        # Add class_id if provided
        if class_id:
            assignment_data["class_id"] = class_id
        
        logger.info(f"💾 Saving assignment to database: {topic} (section: {section}, teacher: {teacher_id})")
        logger.debug(f"   Assignment data: {assignment_data}")
        
        result = supabase.table("assignments").insert(assignment_data).execute()
        
        if result.data and len(result.data) > 0:
            assignment_id = result.data[0]["id"]
            logger.info(f"✓ Assignment saved successfully with ID: {assignment_id}")
            return assignment_id
        else:
            logger.error("❌ No data returned from assignment insertion")
            if hasattr(result, 'error') and result.error:
                logger.error(f"   Error: {result.error}")
            return None
    except Exception as e:
        logger.error(f"❌ Error creating assignment in DB: {e}", exc_info=True)
        return None


def update_assignment_in_db(
    assignment_id: str,
    teacher_id: str,
    topic: Optional[str] = None,
    description: Optional[str] = None,
    assignment_type: Optional[str] = None,
    num_questions: Optional[int] = None,
    questions: Optional[List[Dict[str, Any]]] = None,
    rubric: Optional[Dict[str, Any]] = None,
    published: Optional[bool] = None,
    deadline: Optional[str] = None
) -> bool:
    """Update an assignment in database. Returns True if successful."""
    if not supabase:
        logger.error("❌ Supabase not configured, cannot update assignment")
        return False
    
    try:
        # First verify the assignment belongs to this teacher
        check_result = supabase.table("assignments").select("teacher_id").eq("id", assignment_id).execute()
        if not check_result.data or len(check_result.data) == 0:
            logger.error(f"❌ Assignment {assignment_id} not found")
            return False
        
        if check_result.data[0]["teacher_id"] != teacher_id:
            logger.error(f"❌ Assignment {assignment_id} does not belong to teacher {teacher_id}")
            return False
        
        # Build update data (only include fields that are provided)
        update_data: Dict[str, Any] = {}
        if topic is not None:
            update_data["topic"] = topic
        if description is not None:
            update_data["description"] = description
        if assignment_type is not None:
            update_data["type"] = assignment_type
        if num_questions is not None:
            update_data["num_questions"] = num_questions
        if questions is not None:
            update_data["questions"] = questions
        if rubric is not None:
            update_data["rubric"] = rubric
        if published is not None:
            update_data["published"] = published
        if deadline is not None:
            update_data["due_date"] = deadline
        
        if not update_data:
            logger.warning("No fields to update")
            return False
        
        update_data["updated_at"] = "now()"
        
        logger.info(f"💾 Updating assignment {assignment_id}")
        result = supabase.table("assignments").update(update_data).eq("id", assignment_id).execute()
        
        if result.data and len(result.data) > 0:
            logger.info(f"✓ Assignment updated successfully")
            return True
        else:
            logger.error("❌ No data returned from assignment update")
            return False
    except Exception as e:
        logger.error(f"❌ Error updating assignment in DB: {e}", exc_info=True)
        return False


def delete_assignment_in_db(assignment_id: str, teacher_id: str) -> bool:
    """Delete an assignment from database. Returns True if successful."""
    if not supabase:
        logger.error("❌ Supabase not configured, cannot delete assignment")
        return False
    
    try:
        # First verify the assignment belongs to this teacher
        check_result = supabase.table("assignments").select("teacher_id").eq("id", assignment_id).execute()
        if not check_result.data or len(check_result.data) == 0:
            logger.error(f"❌ Assignment {assignment_id} not found")
            return False
        
        if check_result.data[0]["teacher_id"] != teacher_id:
            logger.error(f"❌ Assignment {assignment_id} does not belong to teacher {teacher_id}")
            return False
        
        logger.info(f"🗑️ Deleting assignment {assignment_id}")
        result = supabase.table("assignments").delete().eq("id", assignment_id).execute()
        
        if result.data or (hasattr(result, 'data') and result.data is not None):
            logger.info(f"✓ Assignment deleted successfully")
            return True
        else:
            logger.error("❌ No data returned from assignment deletion")
            return False
    except Exception as e:
        logger.error(f"❌ Error deleting assignment in DB: {e}", exc_info=True)
        return False


# ============================================================
# CLASS MANAGEMENT FUNCTIONS
# ============================================================

def create_class(name: str, code: Optional[str] = None, description: Optional[str] = None) -> Optional[str]:
    """Create a new class and return class ID."""
    if not supabase:
        logger.error("❌ Supabase not configured, cannot create class")
        return None
    
    try:
        class_data = {
            "name": name,
            "description": description
        }
        if code:
            class_data["code"] = code
        
        logger.info(f"💾 Creating class: {name}")
        result = supabase.table("classes").insert(class_data).execute()
        
        if result.data and len(result.data) > 0:
            class_id = result.data[0]["id"]
            logger.info(f"✓ Class created successfully with ID: {class_id}")
            return class_id
        else:
            logger.error("❌ No data returned from class insertion")
            return None
    except Exception as e:
        logger.error(f"❌ Error creating class in DB: {e}", exc_info=True)
        return None


def assign_teacher_to_class(teacher_id: str, class_id: str) -> bool:
    """Assign a teacher to a class."""
    if not supabase:
        logger.error("❌ Supabase not configured, cannot assign teacher to class")
        return False
    
    try:
        logger.info(f"💾 Assigning teacher {teacher_id} to class {class_id}")
        result = supabase.table("teacher_class").insert({
            "teacher_id": teacher_id,
            "class_id": class_id
        }).execute()
        
        if result.data:
            logger.info(f"✓ Teacher assigned to class successfully")
            return True
        else:
            logger.error("❌ No data returned from teacher_class insertion")
            return False
    except Exception as e:
        logger.error(f"❌ Error assigning teacher to class: {e}", exc_info=True)
        return False


def enroll_student_in_class(student_id: str, class_id: str) -> bool:
    """Enroll a student in a class."""
    if not supabase:
        logger.error("❌ Supabase not configured, cannot enroll student in class")
        return False
    
    try:
        logger.info(f"💾 Enrolling student {student_id} in class {class_id}")
        result = supabase.table("student_class").insert({
            "student_id": student_id,
            "class_id": class_id
        }).execute()
        
        if result.data:
            logger.info(f"✓ Student enrolled in class successfully")
            return True
        else:
            logger.error("❌ No data returned from student_class insertion")
            return False
    except Exception as e:
        logger.error(f"❌ Error enrolling student in class: {e}", exc_info=True)
        return False


def get_teacher_classes(teacher_id: str) -> List[Dict[str, Any]]:
    """Get all classes taught by a teacher."""
    if not supabase:
        return []
    
    try:
        result = supabase.table("teacher_class").select("*, classes(*)").eq("teacher_id", teacher_id).execute()
        if result.data:
            # Flatten the structure
            classes = []
            for tc in result.data:
                class_data = tc.get("classes", {})
                if class_data:
                    classes.append({
                        "id": class_data.get("id"),
                        "name": class_data.get("name"),
                        "code": class_data.get("code"),
                        "description": class_data.get("description")
                    })
            return classes
        return []
    except Exception as e:
        logger.error(f"Error fetching teacher classes: {e}", exc_info=True)
        return []


def get_student_classes(student_id: str) -> List[Dict[str, Any]]:
    """Get all classes a student is enrolled in."""
    if not supabase:
        return []
    
    try:
        result = supabase.table("student_class").select("*, classes(*)").eq("student_id", student_id).execute()
        if result.data:
            # Flatten the structure
            classes = []
            for sc in result.data:
                class_data = sc.get("classes", {})
                if class_data:
                    classes.append({
                        "id": class_data.get("id"),
                        "name": class_data.get("name"),
                        "code": class_data.get("code"),
                        "description": class_data.get("description"),
                        "enrolled_at": sc.get("enrolled_at")
                    })
            return classes
        return []
    except Exception as e:
        logger.error(f"Error fetching student classes: {e}", exc_info=True)
        return []


def get_class_students(class_id: str) -> List[Dict[str, Any]]:
    """Get all students enrolled in a class."""
    if not supabase:
        return []
    
    try:
        result = supabase.table("student_class").select("*, profiles(*)").eq("class_id", class_id).execute()
        if result.data:
            students = []
            for sc in result.data:
                profile = sc.get("profiles", {})
                if profile:
                    students.append({
                        "id": profile.get("id"),
                        "name": profile.get("name"),
                        "email": profile.get("email"),
                        "roll_number": profile.get("roll_number"),
                        "section": profile.get("section"),
                        "enrolled_at": sc.get("enrolled_at")
                    })
            return students
        return []
    except Exception as e:
        logger.error(f"Error fetching class students: {e}", exc_info=True)
        return []


def get_class_teachers(class_id: str) -> List[Dict[str, Any]]:
    """Get all teachers teaching a class."""
    if not supabase:
        return []
    
    try:
        result = supabase.table("teacher_class").select("*, profiles(*)").eq("class_id", class_id).execute()
        if result.data:
            teachers = []
            for tc in result.data:
                profile = tc.get("profiles", {})
                if profile:
                    teachers.append({
                        "id": profile.get("id"),
                        "name": profile.get("name"),
                        "email": profile.get("email")
                    })
            return teachers
        return []
    except Exception as e:
        logger.error(f"Error fetching class teachers: {e}", exc_info=True)
        return []


def get_class_by_code(class_code: str) -> Optional[Dict[str, Any]]:
    """Get a class by its code."""
    if not supabase:
        return None
    
    try:
        result = supabase.table("classes").select("*").eq("code", class_code).single().execute()
        if result.data:
            return result.data
        return None
    except Exception as e:
        # Check if it's a "no rows found" error (expected case, not an error)
        error_str = str(e)
        if "PGRST116" in error_str or "0 rows" in error_str or "Cannot coerce" in error_str:
            # Class not found - this is expected, not an error
            logger.debug(f"Class with code '{class_code}' not found")
            return None
        # For other errors, log as error
        logger.error(f"Error fetching class by code: {e}", exc_info=True)
        return None


def is_student_enrolled(student_id: str, class_id: str) -> bool:
    """Check if a student is already enrolled in a class."""
    if not supabase:
        return False
    
    try:
        result = supabase.table("student_class").select("id").eq("student_id", student_id).eq("class_id", class_id).execute()
        return result.data is not None and len(result.data) > 0
    except Exception as e:
        logger.error(f"Error checking enrollment: {e}", exc_info=True)
        return False


def create_submission_in_db(
    assignment_id: str,
    student_id: str,
    roll_number: Optional[str] = None,
    section: Optional[str] = None,
    file_name: Optional[str] = None,
    file_url: Optional[str] = None,
    answer_text: Optional[str] = None
) -> Optional[str]:
    """Create submission in database and return submission ID."""
    if not supabase:
        logger.warning("Supabase not configured, cannot save submission")
        return None
    
    try:
        submission_data = {
            "assignment_id": assignment_id,
            "student_id": student_id,
            "roll_number": roll_number,
            "section": section if section else "",  # Database requires non-null, use empty string if None
            "file_name": file_name,
            "file_url": file_url,
            "answer_text": answer_text
        }
        
        result = supabase.table("submissions").insert(submission_data).execute()
        if result.data:
            return result.data[0]["id"]
        return None
    except Exception as e:
        logger.error(f"Error creating submission in DB: {e}")
        return None


def update_submission_grade(
    submission_id: str,
    grade: float,
    grade_reason: str,
    plagiarism_score: Optional[float] = None,
    web_sources: Optional[List[Dict[str, Any]]] = None,
    academic_sources: Optional[List[Dict[str, Any]]] = None
) -> bool:
    """Update submission with grade, plagiarism score, and source attribution."""
    if not supabase:
        logger.warning("Supabase not configured, cannot update grade")
        return False
    
    try:
        import json
        update_data: Dict[str, Any] = {
            "grade": grade,
            "grade_reason": grade_reason
        }
        if plagiarism_score is not None:
            update_data["plagiarism_score"] = plagiarism_score
        
        # Add source attribution if provided (store as JSON strings)
        if web_sources:
            update_data["web_sources"] = json.dumps(web_sources) if isinstance(web_sources, list) else web_sources
            logger.info(f"   Including {len(web_sources)} web sources")
        if academic_sources:
            update_data["academic_sources"] = json.dumps(academic_sources) if isinstance(academic_sources, list) else academic_sources
            logger.info(f"   Including {len(academic_sources)} academic sources")
        
        result = supabase.table("submissions").update(update_data).eq("id", submission_id).execute()
        
        if result.data:
            logger.info(f"✓ Updated grade for submission {submission_id}: {grade}")
            return True
        else:
            logger.warning(f"⚠ No data returned when updating submission {submission_id}")
            return False
    except Exception as e:
        logger.error(f"❌ Error updating submission grade: {e}", exc_info=True)
        return False


def create_user_profile(
    email: str,
    name: str,
    role: str,
    password: Optional[str] = None,  # ⚠️ Optional - Supabase Auth handles passwords
    section: Optional[str] = None,
    teacher_id: Optional[str] = None,
    user_id: Optional[str] = None,  # Optional - if provided, use this ID (from Supabase Auth)
    roll_number: Optional[str] = None  # Optional - roll number for students
) -> Optional[Dict[str, Any]]:
    """
    Create a new user profile in the database.
    Uses service role key to bypass RLS.
    
    Returns the created profile or None if error.
    """
    if not supabase:
        logger.error("❌ Supabase client not initialized!")
        logger.error(f"   SUPABASE_URL: {'SET' if SUPABASE_URL else 'NOT SET'}")
        logger.error(f"   SUPABASE_SERVICE_KEY: {'SET' if SUPABASE_SERVICE_KEY else 'NOT SET'}")
        return None
    
    try:
        import uuid
        
        # Use provided user_id (from Supabase Auth) or generate new UUID
        user_id = user_id if user_id else str(uuid.uuid4())
        
        profile_data = {
            "id": user_id,
            "email": email,
            "name": name,
            "role": role,
            # ⚠️ DO NOT store password - Supabase Auth handles passwords
            # Only include password if explicitly provided (for backward compatibility)
        }
        
        # Only add password if provided (for legacy users, but should be None for new users)
        if password is not None:
            logger.warning(f"⚠️ Storing password in profile for {email} - this should be removed!")
            profile_data["password"] = password
        
        # Add optional fields
        if section:
            profile_data["section"] = section
        if teacher_id:
            profile_data["teacher_id"] = teacher_id
        # Only add roll_number if provided and not empty
        # Note: This assumes the roll_number column exists in the database schema
        # If the column doesn't exist, this will fail - you may need to add it via migration
        if roll_number and roll_number.strip():
            profile_data["roll_number"] = roll_number.strip()
        
        logger.info(f"Attempting to create user profile: {email} ({role})")
        logger.debug(f"Profile data: {profile_data}")
        
        # Check if user with this email already exists
        try:
            existing = supabase.table("profiles").select("id, email").eq("email", email).execute()
            if existing.data and len(existing.data) > 0:
                existing_id = existing.data[0]["id"]
                logger.warning(f"⚠️ User with email {email} already exists with ID: {existing_id}")
                # If user_id was provided and it's different, we can't create a duplicate
                # Return the existing profile instead
                if user_id and user_id != existing_id:
                    logger.warning(f"⚠️ Requested user_id {user_id} differs from existing {existing_id}. Returning existing profile.")
                # Fetch and return the full existing profile
                full_profile = supabase.table("profiles").select("*").eq("id", existing_id).single().execute()
                if full_profile.data:
                    logger.info(f"✓ Returning existing user profile: {email} (ID: {existing_id})")
                    return full_profile.data
        except Exception as check_error:
            logger.debug(f"Could not check for existing user: {check_error}")
        
        # Insert using service role (bypasses RLS)
        try:
            result = supabase.table("profiles").insert(profile_data).execute()
        except Exception as e:
            error_str = str(e)
            # If roll_number column doesn't exist, try without it
            if "roll_number" in error_str.lower() and ("column" in error_str.lower() or "PGRST204" in error_str):
                logger.warning(f"⚠️ roll_number column not found in profiles table, creating profile without it")
                profile_data_without_roll = {k: v for k, v in profile_data.items() if k != "roll_number"}
                result = supabase.table("profiles").insert(profile_data_without_roll).execute()
            else:
                raise
        
        logger.debug(f"Supabase response: {result}")
        
        # Check for errors in response
        if hasattr(result, 'error') and result.error:
            logger.error(f"❌ Supabase error: {result.error}")
            return None
        
        if result.data and len(result.data) > 0:
            logger.info(f"✓ User profile created: {email} ({role})")
            return result.data[0]
        else:
            logger.error("❌ No data returned from profile creation")
            logger.error(f"   Response: {result}")
            return None
    except Exception as e:
        logger.error(f"❌ Exception creating user profile: {e}", exc_info=True)
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get user profile by email (for login)."""
    if not supabase:
        return None
    
    try:
        result = supabase.table("profiles").select("*").eq("email", email).single().execute()
        return result.data if result.data else None
    except Exception as e:
        logger.error(f"Error fetching user by email: {e}")
        return None


def find_teacher_by_email(teacher_email: str) -> Optional[Dict[str, Any]]:
    """Find a teacher profile by email (for linking students to teachers)."""
    if not supabase:
        return None
    
    try:
        result = supabase.table("profiles").select("id, email, name, section").eq("email", teacher_email).eq("role", "teacher").single().execute()
        return result.data if result.data else None
    except Exception as e:
        logger.warning(f"Teacher not found with email {teacher_email}: {e}")
        return None


# ============================================================
# ADMIN HELPER FUNCTIONS
# ============================================================

def get_all_users(role: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all users (Admin only). Optionally filter by role."""
    if not supabase:
        return []
    
    try:
        query = supabase.table("profiles").select("*")
        if role:
            query = query.eq("role", role)
        result = query.order("created_at", desc=True).execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error fetching all users: {e}")
        return []


def get_all_classes() -> List[Dict[str, Any]]:
    """Get all classes (Admin only)."""
    if not supabase:
        return []
    
    try:
        result = supabase.table("classes").select("*").order("created_at", desc=True).execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error fetching all classes: {e}")
        return []


def get_all_assignments() -> List[Dict[str, Any]]:
    """Get all assignments (Admin only)."""
    if not supabase:
        return []
    
    try:
        result = supabase.table("assignments").select("*").order("created_at", desc=True).execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error fetching all assignments: {e}")
        return []


def get_all_submissions() -> List[Dict[str, Any]]:
    """Get all submissions (Admin only)."""
    if not supabase:
        return []
    
    try:
        result = supabase.table("submissions").select("*").order("submitted_at", desc=True).execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error fetching all submissions: {e}")
        return []


def update_user_role(user_id: str, new_role: str) -> bool:
    """Update user role (Admin only)."""
    if not supabase:
        return False
    
    if new_role not in ["admin", "teacher", "student"]:
        logger.error(f"Invalid role: {new_role}")
        return False
    
    try:
        result = supabase.table("profiles").update({"role": new_role}).eq("id", user_id).execute()
        return result.data is not None and len(result.data) > 0
    except Exception as e:
        logger.error(f"Error updating user role: {e}")
        return False


def assign_teacher_to_class_admin(class_id: str, teacher_id: str) -> bool:
    """Assign a teacher to a class (Admin only - bypasses ownership checks)."""
    if not supabase:
        return False
    
    try:
        # Check if assignment already exists
        existing = supabase.table("teacher_class").select("*").eq("class_id", class_id).eq("teacher_id", teacher_id).execute()
        if existing.data and len(existing.data) > 0:
            logger.info(f"Teacher {teacher_id} already assigned to class {class_id}")
            return True
        
        # Create assignment
        result = supabase.table("teacher_class").insert({
            "class_id": class_id,
            "teacher_id": teacher_id
        }).execute()
        return result.data is not None and len(result.data) > 0
    except Exception as e:
        logger.error(f"Error assigning teacher to class: {e}")
        return False


def enroll_student_in_class_admin(class_id: str, student_id: str) -> bool:
    """Enroll a student in a class (Admin only - bypasses ownership checks)."""
    if not supabase:
        return False
    
    try:
        # Check if enrollment already exists
        existing = supabase.table("student_class").select("*").eq("class_id", class_id).eq("student_id", student_id).execute()
        if existing.data and len(existing.data) > 0:
            logger.info(f"Student {student_id} already enrolled in class {class_id}")
            return True
        
        # Create enrollment
        result = supabase.table("student_class").insert({
            "class_id": class_id,
            "student_id": student_id
        }).execute()
        return result.data is not None and len(result.data) > 0
    except Exception as e:
        logger.error(f"Error enrolling student in class: {e}")
        return False


def remove_user_from_class(user_id: str, class_id: str, user_role: str) -> bool:
    """Remove a user (teacher or student) from a class (Admin only)."""
    if not supabase:
        return False
    
    try:
        if user_role == "teacher":
            result = supabase.table("teacher_class").delete().eq("class_id", class_id).eq("teacher_id", user_id).execute()
        elif user_role == "student":
            result = supabase.table("student_class").delete().eq("class_id", class_id).eq("student_id", user_id).execute()
        else:
            logger.error(f"Cannot remove user with role {user_role} from class")
            return False
        return True
    except Exception as e:
        logger.error(f"Error removing user from class: {e}")
        return False


def delete_user_profile(user_id: str) -> bool:
    """Delete a user profile (Admin only)."""
    if not supabase:
        return False
    
    try:
        result = supabase.table("profiles").delete().eq("id", user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error deleting user profile: {e}")
        return False


def get_system_stats() -> Dict[str, Any]:
    """Get system-wide statistics (Admin only)."""
    if not supabase:
        return {
            "total_users": 0,
            "total_teachers": 0,
            "total_students": 0,
            "total_admins": 0,
            "total_classes": 0,
            "total_assignments": 0,
            "total_submissions": 0
        }
    
    try:
        # Get user counts by role
        users_result = supabase.table("profiles").select("role").execute()
        users = users_result.data if users_result.data else []
        user_counts = {"admin": 0, "teacher": 0, "student": 0}
        for user in users:
            role = user.get("role", "student")
            if role in user_counts:
                user_counts[role] += 1
        
        # Get class count
        classes_result = supabase.table("classes").select("id", count="exact").execute()
        total_classes = classes_result.count if hasattr(classes_result, 'count') else len(classes_result.data or [])
        
        # Get assignment count
        assignments_result = supabase.table("assignments").select("id", count="exact").execute()
        total_assignments = assignments_result.count if hasattr(assignments_result, 'count') else len(assignments_result.data or [])
        
        # Get submission count
        submissions_result = supabase.table("submissions").select("id", count="exact").execute()
        total_submissions = submissions_result.count if hasattr(submissions_result, 'count') else len(submissions_result.data or [])
        
        return {
            "total_users": len(users),
            "total_teachers": user_counts["teacher"],
            "total_students": user_counts["student"],
            "total_admins": user_counts["admin"],
            "total_classes": total_classes,
            "total_assignments": total_assignments,
            "total_submissions": total_submissions
        }
    except Exception as e:
        logger.error(f"Error fetching system stats: {e}")
        return {
            "total_users": 0,
            "total_teachers": 0,
            "total_students": 0,
            "total_admins": 0,
            "total_classes": 0,
            "total_assignments": 0,
            "total_submissions": 0
        }

