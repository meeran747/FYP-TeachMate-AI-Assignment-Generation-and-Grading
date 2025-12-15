from typing import TypedDict, Optional, List
from pydantic import BaseModel, Field

class Rubric(BaseModel):
    total_points: int = Field(..., description="Total possible points")
    criteria: List[str] = Field(..., description="Criterion name to max points mapping")

class AssignmentCreate(TypedDict):
    topic: str
    description: str
    type: str
    num_questions: int
    questions: List[str]
    rubric: Rubric
    context: str
    is_relevant: Optional[bool]
    relevance_reasoning: Optional[str]
    
class AssignmentRelevanceCheck(BaseModel):
    is_relevant: bool = Field(..., description="Indicates if the content is relevant to the assignment topic")
    reasoning: str = Field(None, description="Explanation for the relevance decision")

class AssignmentMaker(BaseModel):
    questions: List[str] = Field(..., description="List of generated questions for the assignment")

# Grading-related models
class RubricGrade(BaseModel):
    total_score: float = Field(..., description="Total score awarded")
    reason: str = Field(..., description="Explanation for the grade")

class SourceMatch(BaseModel):
    url: str = Field(..., description="URL of the matched source")
    title: Optional[str] = Field(None, description="Title of the source")
    similarity: float = Field(..., description="Similarity score (0-100)")
    snippet: Optional[str] = Field(None, description="Matching text snippet")

class Submissions(BaseModel):
    submission_id: str = Field(..., description="Submission ID")
    file_url: Optional[str] = Field(None, description="URL to the submitted file")
    file_content: Optional[str] = Field(None, description="Parsed content of the submitted file")
    plagerism_score: Optional[float] = Field(None, description="Plagiarism similarity score (0-100)")
    total_score: Optional[RubricGrade] = Field(None, description="Grading result")
    web_sources: Optional[List[SourceMatch]] = Field(None, description="Matched web sources")
    academic_sources: Optional[List[SourceMatch]] = Field(None, description="Matched academic sources")

class AssignmentGrade(TypedDict, total=False):
    assignment_id: str
    submission_ids: List[Submissions]
    rubric: Optional[str]
    questions: Optional[str]
    student_ids: Optional[List[str]]  # Filter submissions to only these students