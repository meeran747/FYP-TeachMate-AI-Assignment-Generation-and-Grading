"""
Analytics helper functions for teacher dashboard.
Calculates submission rates, average grades, and late submission percentages.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
from db_helpers import supabase, get_teacher_students, get_teacher_submissions, get_class_students

logger = logging.getLogger(__name__)


def get_assignment_analytics(teacher_id: str, assignment_id: Optional[str] = None, class_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get analytics for a teacher's assignments.
    
    Returns:
    - For each assignment:
      - submission_rate: percentage of enrolled students who submitted
      - average_grade: average grade across all submissions
      - late_submissions_pct: percentage of submissions that were late
      - students_submitted: number of students who submitted
      - students_pending: number of students who haven't submitted
      - total_students: total number of enrolled students
    """
    if not supabase:
        logger.error("Supabase not configured")
        return {"assignments": [], "error": "Database not configured"}
    
    try:
        # Get students - if class_id is provided, only get students from that class
        if class_id:
            students = get_class_students(class_id)
            # Verify this class belongs to the teacher
            teacher_classes_result = supabase.table("teacher_class").select("class_id").eq("teacher_id", teacher_id).eq("class_id", class_id).execute()
            if not teacher_classes_result.data:
                return {
                    "assignments": [],
                    "total_students": 0,
                    "error": "Class not found or you don't have access to this class"
                }
        else:
            students = get_teacher_students(teacher_id)
        total_students = len(students)
        student_ids = [s["id"] for s in students]
        
        if total_students == 0:
            return {
                "assignments": [],
                "total_students": 0,
                "message": "No students enrolled in your classes"
            }
        
        # Get all assignments created by this teacher
        query = supabase.table("assignments").select("*").eq("teacher_id", teacher_id)
        if assignment_id:
            query = query.eq("id", assignment_id)
        if class_id:
            query = query.eq("class_id", class_id)
        if not assignment_id:
            query = query.order("created_at", desc=True)
        
        assignments_result = query.execute()
        assignments = assignments_result.data if assignments_result.data else []
        
        if not assignments:
            return {
                "assignments": [],
                "total_students": total_students,
                "message": "No assignments found"
            }
        
        analytics = []
        
        for assignment in assignments:
            assignment_id = assignment["id"]
            due_date = assignment.get("due_date")
            
            # Get all submissions for this assignment
            submissions = get_teacher_submissions(teacher_id, assignment_id)
            
            # Calculate metrics
            students_submitted = len(submissions)
            students_pending = total_students - students_submitted
            submission_rate = (students_submitted / total_students * 100) if total_students > 0 else 0
            
            # Calculate average grade
            graded_submissions = [s for s in submissions if s.get("total_score") is not None]
            if graded_submissions:
                total_score = sum(float(s.get("total_score", 0)) for s in graded_submissions)
                average_grade = total_score / len(graded_submissions)
            else:
                average_grade = None
            
            # Calculate late submissions percentage
            late_count = 0
            if due_date:
                due_datetime = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                for submission in submissions:
                    submitted_at = submission.get("submitted_at")
                    if submitted_at:
                        submitted_datetime = datetime.fromisoformat(submitted_at.replace('Z', '+00:00'))
                        if submitted_datetime > due_datetime:
                            late_count += 1
                
                late_submissions_pct = (late_count / students_submitted * 100) if students_submitted > 0 else 0
            else:
                late_submissions_pct = 0
            
            analytics.append({
                "assignment_id": assignment_id,
                "topic": assignment.get("topic", "Untitled"),
                "class_id": assignment.get("class_id"),
                "due_date": due_date,
                "created_at": assignment.get("created_at"),
                "published": assignment.get("published", False),
                "submission_rate": round(submission_rate, 2),
                "average_grade": round(average_grade, 2) if average_grade is not None else None,
                "late_submissions_pct": round(late_submissions_pct, 2),
                "students_submitted": students_submitted,
                "students_pending": students_pending,
                "total_students": total_students,
                "graded_count": len(graded_submissions),
                "total_submissions": len(submissions)
            })
        
        return {
            "assignments": analytics,
            "total_students": total_students,
            "total_assignments": len(analytics)
        }
    
    except Exception as e:
        logger.error(f"Error calculating analytics: {e}", exc_info=True)
        return {"assignments": [], "error": str(e)}


def get_overall_analytics(teacher_id: str, class_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get overall analytics across all assignments for a teacher.
    Optionally filter by class_id.
    """
    analytics = get_assignment_analytics(teacher_id, class_id=class_id)
    
    if "error" in analytics or not analytics.get("assignments"):
        return {
            "total_students": analytics.get("total_students", 0),
            "total_assignments": 0,
            "overall_submission_rate": 0,
            "overall_average_grade": None,
            "overall_late_pct": 0
        }
    
    assignments = analytics["assignments"]
    
    # Calculate overall metrics
    total_submissions = sum(a["students_submitted"] for a in assignments)
    total_possible = sum(a["total_students"] for a in assignments) if assignments else 0
    overall_submission_rate = (total_submissions / total_possible * 100) if total_possible > 0 else 0
    
    # Overall average grade (weighted by number of submissions)
    graded_assignments = [a for a in assignments if a["average_grade"] is not None]
    if graded_assignments:
        total_weighted_grade = sum(a["average_grade"] * a["graded_count"] for a in graded_assignments)
        total_graded = sum(a["graded_count"] for a in graded_assignments)
        overall_average_grade = total_weighted_grade / total_graded if total_graded > 0 else None
    else:
        overall_average_grade = None
    
    # Overall late percentage
    total_late = sum(
        (a["late_submissions_pct"] / 100) * a["students_submitted"] 
        for a in assignments if a["students_submitted"] > 0
    )
    overall_late_pct = (total_late / total_submissions * 100) if total_submissions > 0 else 0
    
    return {
        "total_students": analytics["total_students"],
        "total_assignments": len(assignments),
        "overall_submission_rate": round(overall_submission_rate, 2),
        "overall_average_grade": round(overall_average_grade, 2) if overall_average_grade is not None else None,
        "overall_late_pct": round(overall_late_pct, 2),
        "assignments": assignments
    }

