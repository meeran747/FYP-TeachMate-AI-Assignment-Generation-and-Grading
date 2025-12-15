import React, { useState, useEffect } from 'react';
import { apiService, createDevToken } from '../services/api';
import { useToast } from '../hooks/useToast';
import Toast from './Toast';
import AnalyticsDashboard from './AnalyticsDashboard';
import Settings from './Settings';
import './Dashboard.css';
import './CommonStyles.css';
import './AssignmentCard.css';

interface TeacherDashboardProps {
  user: any;
  profile: any;
  onSignOut: () => void;
}

interface Rubric {
  total_points: number;
  criteria: string[];
}

const TeacherDashboard: React.FC<TeacherDashboardProps> = ({ user, profile, onSignOut }) => {
  const { toasts, showToast, removeToast } = useToast();
  const [showCreateAssignment, setShowCreateAssignment] = useState(false);
  const [assignmentForm, setAssignmentForm] = useState({
    topic: '',
    description: '',
    type: 'theoretical',
    num_questions: 5,
    deadline: '',
    published: false
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [generatedQuestions, setGeneratedQuestions] = useState<string[]>([]);
  const [generatedRubric, setGeneratedRubric] = useState<Rubric | null>(null);
  const [showQuestions, setShowQuestions] = useState(false);
  const [assignments, setAssignments] = useState<any[]>([]);
  const [showAssignments, setShowAssignments] = useState(false);
  const [loadingAssignments, setLoadingAssignments] = useState(false);
  const [assignmentSubmissions, setAssignmentSubmissions] = useState<{[key: string]: any[]}>({});
  const [loadingSubmissions, setLoadingSubmissions] = useState<{[key: string]: boolean}>({});
  const [showGradingModal, setShowGradingModal] = useState(false);
  const [gradingAssignmentId, setGradingAssignmentId] = useState<string | null>(null);
  const [isGrading, setIsGrading] = useState(false);
  const [selectedSubmission, setSelectedSubmission] = useState<any>(null);
  const [showSubmissionModal, setShowSubmissionModal] = useState(false);
  const [editingAssignment, setEditingAssignment] = useState<any>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editForm, setEditForm] = useState({
    topic: '',
    description: '',
    type: 'theoretical',
    num_questions: 5,
    deadline: ''
  });
  const [classes, setClasses] = useState<any[]>([]);
  const [selectedClassId, setSelectedClassId] = useState<string | null>(null);
  const [showCreateClassModal, setShowCreateClassModal] = useState(false);
  const [classForm, setClassForm] = useState({
    name: '',
    code: '',
    description: ''
  });
  const [classStudents, setClassStudents] = useState<any[]>([]);
  const [showClassStudents, setShowClassStudents] = useState(false);
  const [expandedClassId, setExpandedClassId] = useState<string | null>(null);
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [analyticsClassId, setAnalyticsClassId] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value, type, checked } = e.target as HTMLInputElement;
    setAssignmentForm(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : (name === 'num_questions' ? parseInt(value) || 5 : value)
    }));
  };

  const loadClasses = async () => {
    try {
      const result = await apiService.getMyClasses();
      if (result.success && result.classes) {
        setClasses(result.classes);
        // Auto-select first class if available
        if (result.classes.length > 0 && !selectedClassId) {
          setSelectedClassId(result.classes[0].id);
        }
      }
    } catch (error: any) {
      console.error('Error loading classes:', error);
      showToast(error.message || 'Failed to load classes', 'error');
    }
  };

  // Set up auth token on mount
  useEffect(() => {
    if (user && profile) {
      const token = createDevToken(user.id, user.email, profile.role, profile.name);
      localStorage.setItem('auth_token', token);
    }
    loadClasses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, profile]);

  const handleGenerateAssignment = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!selectedClassId) {
      showToast('Please select a class first before creating an assignment', 'warning');
      return;
    }
    
    setIsSubmitting(true);
    setGeneratedQuestions([]);
    setGeneratedRubric(null);

    try {
      console.log('Calling RBAC API to generate assignment...');
      
      // Use new RBAC API service
      const result = await apiService.createAssignment({
        topic: assignmentForm.topic,
        description: assignmentForm.description,
        type: assignmentForm.type,
        num_questions: assignmentForm.num_questions,
        section: '', // Optional - not used in class-based system
        deadline: assignmentForm.deadline || undefined,
        published: assignmentForm.published,
        class_id: selectedClassId || undefined
      });

      console.log('Assignment generated:', result);

      if (result.success && result.questions && result.questions.length > 0) {
        setGeneratedQuestions(result.questions);
        setGeneratedRubric(result.rubric || null);
        setShowQuestions(true);
        
        // If assignment was saved automatically (has assignment_id), show success
        if (result.assignment_id) {
          showToast(`✓ Assignment created and saved with ${result.questions.length} questions!`, 'success');
          // Refresh assignments list
          loadAssignments();
        } else {
          // Questions generated but not saved - show error message from backend
          const errorMsg = result.message || `Generated ${result.questions.length} questions but failed to save to database.`;
          showToast(errorMsg, 'error');
        }
      } else {
        showToast(result.message || 'Failed to generate questions. Please try again.', 'error');
      }
    } catch (error: any) {
      console.error('Error generating assignment:', error);
      showToast(error.message || 'Failed to connect to AI service. Make sure backend is running on port 8000.', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSaveToDatabase = async () => {
    // Note: With RBAC, assignments are automatically saved when created via API
    // This function is kept for backward compatibility but may not be needed
    if (generatedQuestions.length === 0) {
      showToast('Please generate questions first', 'warning');
      return;
    }

    showToast('Assignment is automatically saved when created. Use "Generate Questions" to create and save.', 'info');
  };

  const loadAssignments = async () => {
    setLoadingAssignments(true);
    try {
      console.log('Loading assignments for teacher:', user);
      
      // Use RBAC API endpoint which filters by role
      const result = await apiService.getMyAssignments(selectedClassId || undefined);
      
      console.log('Teacher assignments result:', result);

      if (result.success && result.assignments) {
        console.log('Teacher found assignments:', result.assignments.length);
        if (result.assignments.length > 0) {
          console.log('First assignment questions:', result.assignments[0].questions);
          console.log('First assignment rubric:', result.assignments[0].rubric);
          setAssignments(result.assignments);
          setShowAssignments(true);
        } else {
          setAssignments([]);
          setShowAssignments(true);
        }
      } else {
        setAssignments([]);
        showToast('No assignments found', 'info');
      }
    } catch (error: any) {
      console.error('Error loading assignments:', error);
      showToast(error.message || 'Failed to load assignments', 'error');
      setAssignments([]);
    } finally {
      setLoadingAssignments(false);
    }
  };

  const loadSubmissions = async (assignmentId: string) => {
    if (loadingSubmissions[assignmentId]) return;
    
    setLoadingSubmissions(prev => ({ ...prev, [assignmentId]: true }));
    
    try {
      const result = await apiService.getSubmissions(assignmentId);
      
      if (result.success && result.submissions) {
        setAssignmentSubmissions(prev => ({
          ...prev,
          [assignmentId]: result.submissions
        }));
      }
    } catch (error: any) {
      console.error('Error loading submissions:', error);
      showToast(error.message || 'Failed to load submissions', 'error');
    } finally {
      setLoadingSubmissions(prev => ({ ...prev, [assignmentId]: false }));
    }
  };
  

  const downloadFile = async (fileUrl: string, fileName: string) => {
    try {
      window.open(fileUrl, '_blank');
    } catch (error) {
      console.error('Error downloading file:', error);
      alert('Failed to download file');
    }
  };

  const handleGradeAssignment = async (assignmentId: string) => {
    setIsGrading(true);
    setGradingAssignmentId(assignmentId);
    
    try {
      showToast('Starting AI grading process... This may take a few minutes.', 'info');
      
      const result = await apiService.gradeAssignment(assignmentId);
      
      if (result.success) {
        showToast(
          `✓ Successfully graded ${result.graded_count} submission(s)!`,
          'success'
        );
        
        // Reload submissions to show grades
        await loadSubmissions(assignmentId);
        
        // Reload assignments to refresh submission counts
        await loadAssignments();
      } else {
        showToast('Grading completed with some errors', 'warning');
      }
    } catch (error: any) {
      console.error('Error grading assignment:', error);
      showToast(error.message || 'Failed to grade assignment', 'error');
    } finally {
      setIsGrading(false);
      setGradingAssignmentId(null);
    }
  };

  const handleExportGrades = async (assignmentId: string) => {
    try {
      showToast('Exporting grades to CSV...', 'info');
      await apiService.exportGradesCSV(assignmentId);
      showToast('✓ Grades exported successfully!', 'success');
    } catch (error: any) {
      console.error('Error exporting grades:', error);
      showToast(error.message || 'Failed to export grades', 'error');
    }
  };

  return (
    <div className="dashboard">
      {toasts.map(toast => (
        <Toast
          key={toast.id}
          message={toast.message}
          type={toast.type}
          onClose={() => removeToast(toast.id)}
        />
      ))}
      <header className="dashboard-header">
        <div className="header-content">
          <h1>TeachMate</h1>
          <div className="user-info">
            <span>Welcome, {profile.name}!</span>
            <div className="header-actions">
              <button onClick={() => setShowSettings(true)} className="settings-button" title="Settings">
                ⚙️
              </button>
              <button onClick={onSignOut} className="signout-button">
                Sign Out
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="dashboard-main">
        {showAnalytics ? (
          <AnalyticsDashboard classId={analyticsClassId} onClose={() => { setShowAnalytics(false); setAnalyticsClassId(null); }} />
        ) : (
          <div className="dashboard-content">
            <div className="section-header">
              <h2>Teacher Tools</h2>
              <p>Manage your classes and assignments</p>
            </div>

          {/* Class Selection */}
          <div className="class-selection-container">
            <div className="class-selection-header">
              <h3>Select Class</h3>
              <button
                onClick={() => setShowCreateClassModal(true)}
                className="btn-primary"
              >
                + Create New Class
              </button>
            </div>
            {classes.length === 0 ? (
              <div className="empty-state-container">
                <p>You don't have any classes yet. Create your first class to get started!</p>
                <button
                  onClick={() => setShowCreateClassModal(true)}
                  className="btn-primary"
                  style={{ padding: '10px 20px' }}
                >
                  + Create Your First Class
                </button>
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {classes.map((cls) => (
                    <div
                      key={cls.id}
                      className={expandedClassId === cls.id ? 'class-card-expanded' : 'class-card-normal'}
                    >
                      {/* Class Header - Clickable to expand/collapse */}
                      <div
                        onClick={() => {
                          if (expandedClassId === cls.id) {
                            // Collapse
                            setExpandedClassId(null);
                            setSelectedClassId(null);
                          } else {
                            // Expand
                            setExpandedClassId(cls.id);
                            setSelectedClassId(cls.id);
                          }
                        }}
                        className={expandedClassId === cls.id ? 'class-header-expanded' : 'class-header-normal'}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span style={{ fontSize: '18px' }}>
                            {expandedClassId === cls.id ? '▼' : '▶'}
                          </span>
                          <span>
                            {cls.name} {cls.code && `(${cls.code})`}
                          </span>
                        </div>
                        {expandedClassId === cls.id && (
                          <div style={{ display: 'flex', gap: '10px' }}>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setAnalyticsClassId(cls.id);
                                setShowAnalytics(true);
                              }}
                              className="btn-success"
                            >
                              📊 View Analytics
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                // View students
                                (async () => {
                                  try {
                                    const result = await apiService.getClassStudents(cls.id);
                                    if (result.success) {
                                      setClassStudents(result.students || []);
                                      setShowClassStudents(true);
                                    }
                                  } catch (error: any) {
                                  showToast(error.message || 'Failed to load students', 'error');
                                }
                              })();
                            }}
                            className="btn-outline"
                          >
                            👥 View Students
                            </button>
                          </div>
                        )}
                      </div>

                      {/* Class Actions - Only show when expanded */}
                      {expandedClassId === cls.id && (
                        <div className="class-actions-container">
                          <div className="teacher-actions" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '15px' }}>
            <div className="action-card" onClick={() => setShowCreateAssignment(true)}>
              <div className="action-icon">📝</div>
              <h3>Create Assignment</h3>
                              <p>Generate a new assignment for this class</p>
            </div>

            <div className="action-card" onClick={loadAssignments}>
              <div className="action-icon">📚</div>
              <h3>View Assignments</h3>
                              <p>View all assignments for this class</p>
            </div>

                            <div className="action-card" onClick={() => {
                              setShowGradingModal(true);
                              if (assignments.length === 0) {
                                loadAssignments();
                              }
                            }}>
              <div className="action-icon">✅</div>
              <h3>Grade Assignments</h3>
              <p>Review and grade student submissions</p>
            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {showAssignments && (
            <div className="modal-overlay" onClick={() => setShowAssignments(false)}>
              <div className="modal-content" style={{ maxWidth: '900px', maxHeight: '90vh', overflowY: 'auto' }} onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                  <h3>My AI-Generated Assignments</h3>
                  <button 
                    className="close-button"
                    onClick={() => setShowAssignments(false)}
                  >
                    ×
                  </button>
                </div>

                {loadingAssignments ? (
                  <div style={{ textAlign: 'center', padding: '20px' }}>
                    Loading assignments...
                  </div>
                ) : assignments.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '40px', color: '#666' }}>
                    <p>No assignments created yet.</p>
                    <button 
                      className="submit-button"
                      onClick={() => {
                        setShowAssignments(false);
                        setShowCreateAssignment(true);
                      }}
                      style={{ marginTop: '20px' }}
                    >
                      Create Your First Assignment
                    </button>
                  </div>
                ) : (
                  <div style={{ padding: '20px' }}>
                    {assignments.map((assignment) => (
                      <div key={assignment.id} className="assignment-card-container">
                        <div className="assignment-card-header">
                          <div className="assignment-title-section">
                            <div className="assignment-title-row">
                              <h3 className="assignment-title">{assignment.topic}</h3>
                              <span className={assignment.published ? 'status-badge-published-inline' : 'status-badge-draft-inline'}>
                                {assignment.published ? '✓ Published' : '✗ Draft'}
                              </span>
                            </div>
                            <p className="assignment-description">{assignment.description}</p>
                            <div className="assignment-meta-info">
                              <div className="meta-item">
                                <span className="meta-label">Type:</span>
                                <span className="meta-value">{assignment.type}</span>
                              </div>
                              <div className="meta-item">
                                <span className="meta-label">Questions:</span>
                                <span className="meta-value">{assignment.num_questions}</span>
                              </div>
                              {assignment.deadline && (
                                <div className="meta-item">
                                  <span className="meta-label">Deadline:</span>
                                  <span className="meta-value">
                                    {new Date(assignment.deadline).toLocaleString('en-US', {
                                      year: 'numeric',
                                      month: 'long',
                                      day: 'numeric',
                                      hour: '2-digit',
                                      minute: '2-digit'
                                    })}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                          <div className="assignment-actions-header">
                            <div className="action-buttons-group">
                              <button
                                onClick={() => {
                                  setEditingAssignment(assignment);
                                  setEditForm({
                                    topic: assignment.topic,
                                    description: assignment.description || '',
                                    type: assignment.type,
                                    num_questions: assignment.num_questions,
                                    deadline: assignment.deadline ? new Date(assignment.deadline).toISOString().slice(0, 16) : ''
                                  });
                                  setShowEditModal(true);
                                }}
                                className="btn-icon btn-edit"
                              >
                                ✏️ Edit
                              </button>
                              <button
                                onClick={async () => {
                                  if (window.confirm(`Are you sure you want to delete "${assignment.topic}"? This action cannot be undone.`)) {
                                    try {
                                      await apiService.deleteAssignment(assignment.id);
                                      showToast('✓ Assignment deleted successfully', 'success');
                                      loadAssignments();
                                    } catch (error: any) {
                                      showToast(error.message || 'Failed to delete assignment', 'error');
                                    }
                                  }
                                }}
                                className="btn-icon btn-delete"
                              >
                                🗑️ Delete
                              </button>
                              {assignment.published ? (
                                <button
                                  onClick={async () => {
                                    try {
                                      await apiService.updateAssignment(assignment.id, {
                                        topic: assignment.topic,
                                        description: assignment.description,
                                        type: assignment.type,
                                        num_questions: assignment.num_questions,
                                        deadline: assignment.deadline || undefined,
                                        published: false
                                      });
                                      showToast('✓ Assignment unpublished (now a draft)', 'success');
                                      loadAssignments();
                                    } catch (error: any) {
                                      showToast(error.message || 'Failed to unpublish assignment', 'error');
                                    }
                                  }}
                                  className="btn-icon btn-unpublish"
                                >
                                  📝 Unpublish
                                </button>
                              ) : (
                                <button
                                  onClick={async () => {
                                    try {
                                      await apiService.updateAssignment(assignment.id, {
                                        topic: assignment.topic,
                                        description: assignment.description,
                                        type: assignment.type,
                                        num_questions: assignment.num_questions,
                                        deadline: assignment.deadline || undefined,
                                        published: true
                                      });
                                      showToast('✓ Assignment published! Students can now see it.', 'success');
                                      loadAssignments();
                                    } catch (error: any) {
                                      showToast(error.message || 'Failed to publish assignment', 'error');
                                    }
                                  }}
                                  className="btn-icon btn-publish"
                                >
                                  📢 Publish
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="assignment-details-section">
                          <div className="details-list">
                            <details className="detail-item">
                              <summary className="detail-summary">
                                <span>
                                  <span className="detail-icon">▶</span>
                                  View Questions ({Array.isArray(assignment.questions) ? assignment.questions.length : 0})
                                </span>
                              </summary>
                              <div className="detail-content">
                                <div className="questions-list">
                                  {Array.isArray(assignment.questions) && assignment.questions.map((question: string, idx: number) => (
                                    <div key={idx} className="question-item">
                                      <span className="question-number">Q{idx + 1}:</span>
                                      <span className="question-text">{question}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </details>

                            {assignment.rubric && assignment.rubric.total_points && (
                              <details className="detail-item">
                                <summary className="detail-summary">
                                  <span>
                                    <span className="detail-icon">▶</span>
                                    View Rubric ({assignment.rubric.total_points} points)
                                  </span>
                                </summary>
                                <div className="detail-content">
                                  <div className="rubric-container">
                                    <div className="rubric-points">
                                      Total Points: {assignment.rubric.total_points}
                                    </div>
                                    {assignment.rubric.criteria && Array.isArray(assignment.rubric.criteria) && (
                                      <div>
                                        <strong style={{ color: 'var(--text-primary)', marginBottom: '8px', display: 'block' }}>Grading Criteria:</strong>
                                        <ul className="rubric-criteria">
                                          {assignment.rubric.criteria.map((criterion: string, idx: number) => (
                                            <li key={idx}>{criterion}</li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </details>
                            )}

                            <details 
                              className="detail-item"
                              onToggle={(e: any) => {
                                if (e.target.open && !assignmentSubmissions[assignment.id]) {
                                  loadSubmissions(assignment.id);
                                }
                              }}
                            >
                              <summary className="detail-summary">
                                <span>
                                  <span className="detail-icon">▶</span>
                                  📥 View Submissions ({assignmentSubmissions[assignment.id]?.length || '?'})
                                </span>
                              </summary>
                              <div className="detail-content">
                                {loadingSubmissions[assignment.id] ? (
                                  <div className="loading-submissions">
                                    Loading submissions...
                                  </div>
                                ) : !assignmentSubmissions[assignment.id] || assignmentSubmissions[assignment.id].length === 0 ? (
                                  <div className="empty-submissions">
                                    No submissions yet
                                  </div>
                                ) : (
                                  <div className="submissions-container">
                                    {assignmentSubmissions[assignment.id].map((submission: any, idx: number) => (
                                      <div key={submission.id} className="submission-item">
                                        <div className="submission-header">
                                          <span className="submission-number">Submission #{idx + 1}</span>
                                          <span className="submission-date">
                                            {new Date(submission.submitted_at).toLocaleString()}
                                          </span>
                                        </div>
                                        <div className="submission-details">
                                          <div className="submission-detail-row">
                                            <span className="submission-detail-label">Student:</span>
                                            <span className="submission-detail-value">{submission.profiles?.name || 'N/A'}</span>
                                          </div>
                                          <div className="submission-detail-row">
                                            <span className="submission-detail-label">Roll Number:</span>
                                            <span className="submission-detail-value">{submission.roll_number}</span>
                                          </div>
                                          {submission.grade !== null && submission.grade !== undefined && (
                                            <div className="submission-detail-row">
                                              <span className="submission-detail-label">Grade:</span>
                                              <span className="submission-detail-value">
                                                {submission.grade} / {assignment.rubric?.total_points || 'N/A'}
                                              </span>
                                            </div>
                                          )}
                                          {submission.plagiarism_score !== null && submission.plagiarism_score !== undefined && (
                                            <div className="submission-detail-row">
                                              <span className="submission-detail-label">Plagiarism Score:</span>
                                              <span className="submission-detail-value">{submission.plagiarism_score}%</span>
                                            </div>
                                          )}
                                        </div>
                                        <div className="submission-actions">
                                          <button
                                            onClick={() => {
                                              setSelectedSubmission(submission);
                                              setShowSubmissionModal(true);
                                            }}
                                            className="btn-view-submission"
                                          >
                                            📄 View Full Submission
                                          </button>
                                          {submission.file_url && (
                                            <button
                                              onClick={() => downloadFile(submission.file_url, submission.file_name)}
                                              className="btn-download"
                                            >
                                              📥 Download File
                                            </button>
                                          )}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </details>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {showCreateAssignment && (
            <div className="modal-overlay" onClick={() => {
              setShowCreateAssignment(false);
              setGeneratedQuestions([]);
              setShowQuestions(false);
            }}>
              <div className="modal-content" style={{ maxWidth: '800px', maxHeight: '90vh', overflowY: 'auto' }} onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                  <h3>Create AI-Generated Assignment</h3>
                  <button 
                    className="close-button"
                    onClick={() => {
                      setShowCreateAssignment(false);
                      setGeneratedQuestions([]);
                      setShowQuestions(false);
                    }}
                  >
                    ×
                  </button>
                </div>

                <form onSubmit={handleGenerateAssignment} className="assignment-form">
                  <div className="form-group">
                    <label htmlFor="topic">Assignment Topic *</label>
                    <input
                      type="text"
                      id="topic"
                      name="topic"
                      value={assignmentForm.topic}
                      onChange={handleInputChange}
                      required
                      placeholder="e.g., Data warehouse, Machine Learning, etc."
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="description">Description *</label>
                    <textarea
                      id="description"
                      name="description"
                      value={assignmentForm.description}
                      onChange={handleInputChange}
                      required
                      rows={4}
                      placeholder="Describe what the assignment should cover (e.g., Create an assignment covering ETL)"
                    />
                  </div>


                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="type">Assignment Type *</label>
                      <select
                        id="type"
                        name="type"
                        value={assignmentForm.type}
                        onChange={handleInputChange}
                        required
                      >
                        <option value="theoretical">Theoretical</option>
                        <option value="programming">Programming</option>
                        <option value="multiple_choice">Multiple Choice</option>
                      </select>
                    </div>

                    <div className="form-group">
                      <label htmlFor="num_questions">Number of Questions *</label>
                      <input
                        type="number"
                        id="num_questions"
                        name="num_questions"
                        value={assignmentForm.num_questions}
                        onChange={handleInputChange}
                        min="1"
                        max="50"
                        required
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label htmlFor="deadline">Deadline (Optional)</label>
                    <input
                      type="datetime-local"
                      id="deadline"
                      name="deadline"
                      value={assignmentForm.deadline}
                      onChange={handleInputChange}
                    />
                  </div>

                  <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <input
                      type="checkbox"
                      id="published"
                      name="published"
                      checked={assignmentForm.published}
                      onChange={handleInputChange}
                      style={{ width: 'auto', cursor: 'pointer' }}
                    />
                    <label htmlFor="published" style={{ margin: 0, cursor: 'pointer' }}>
                      Publish assignment (make visible to students)
                    </label>
                  </div>

                  {!showQuestions && (
                    <div className="form-actions">
                      <button 
                        type="button" 
                        className="cancel-button"
                        onClick={() => {
                          setShowCreateAssignment(false);
                          setGeneratedQuestions([]);
                        }}
                      >
                        Cancel
                      </button>
                      <button 
                        type="submit" 
                        className="submit-button"
                        disabled={isSubmitting}
                      >
                        {isSubmitting ? 'Generating...' : '🤖 Generate Questions'}
                      </button>
                    </div>
                  )}
                </form>

                {showQuestions && generatedQuestions.length > 0 && (
                  <div className="generated-questions" style={{ marginTop: '20px' }}>
                    <h4>Generated Questions:</h4>
                    <div style={{ 
                      background: '#f5f5f5', 
                      padding: '15px', 
                      borderRadius: '8px',
                      marginTop: '10px'
                    }}>
                      {generatedQuestions.map((question, index) => (
                        <div key={index} style={{ 
                          marginBottom: '15px',
                          padding: '10px',
                          background: 'white',
                          borderRadius: '5px',
                          borderLeft: '3px solid #667eea'
                        }}>
                          <strong>Question {index + 1}:</strong>
                          <p style={{ marginTop: '5px', marginBottom: '0' }}>{question}</p>
                        </div>
                      ))}
                    </div>

                    {generatedRubric && (
                      <div style={{ marginTop: '20px' }}>
                        <h4>Generated Rubric:</h4>
                        <div style={{ 
                          background: '#f0f7ff', 
                          padding: '15px', 
                          borderRadius: '8px',
                          marginTop: '10px',
                          border: '1px solid #d0e7ff'
                        }}>
                          <div style={{ 
                            marginBottom: '15px',
                            padding: '10px',
                            background: 'white',
                            borderRadius: '5px',
                            borderLeft: '4px solid #4299e1'
                          }}>
                            <strong>Total Points:</strong> {generatedRubric.total_points}
                          </div>
                          <div style={{ marginTop: '10px' }}>
                            <strong>Grading Criteria:</strong>
                            <ul style={{ marginTop: '10px', paddingLeft: '20px' }}>
                              {generatedRubric.criteria.map((criterion, index) => (
                                <li key={index} style={{ marginBottom: '8px', color: '#2d3748' }}>
                                  {criterion}
                                </li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      </div>
                    )}

                    <div className="form-actions" style={{ marginTop: '20px' }}>
                      <button 
                        type="button" 
                        className="cancel-button"
                        onClick={() => {
                          setGeneratedQuestions([]);
                          setGeneratedRubric(null);
                          setShowQuestions(false);
                        }}
                      >
                        Regenerate
                      </button>
                      <button 
                        type="button" 
                        className="submit-button"
                        onClick={handleSaveToDatabase}
                        disabled={isSubmitting}
                      >
                        {isSubmitting ? 'Saving...' : '💾 Save to Database'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {showGradingModal && (
            <div className="modal-overlay" onClick={() => setShowGradingModal(false)}>
              <div className="modal-content" style={{ maxWidth: '900px', maxHeight: '90vh', overflowY: 'auto' }} onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                  <h3>Grade Assignments</h3>
                  <button 
                    className="close-button"
                    onClick={() => setShowGradingModal(false)}
                    disabled={isGrading}
                  >
                    ×
                  </button>
                </div>

                {loadingAssignments ? (
                  <div style={{ textAlign: 'center', padding: '20px' }}>
                    Loading assignments...
                  </div>
                ) : assignments.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '40px', color: '#666' }}>
                    <p>No assignments found.</p>
                    <button 
                      className="submit-button"
                      onClick={() => {
                        setShowGradingModal(false);
                        setShowCreateAssignment(true);
                      }}
                      style={{ marginTop: '20px' }}
                    >
                      Create Your First Assignment
                    </button>
                  </div>
                ) : (
                  <div style={{ padding: '20px' }}>
                    <p style={{ marginBottom: '20px', color: '#666' }}>
                      Select an assignment to grade all submissions using AI. The system will:
                      <ul style={{ marginTop: '10px', paddingLeft: '20px' }}>
                        <li>Download and parse all submission files</li>
                        <li>Grade each submission using the assignment rubric</li>
                        <li>Check for plagiarism between submissions</li>
                        <li>Update grades in the database</li>
                      </ul>
                    </p>
                    
                    {assignments.map((assignment) => {
                      const submissions = assignmentSubmissions[assignment.id] || [];
                      const hasSubmissions = submissions.length > 0;
                      const isCurrentlyGrading = isGrading && gradingAssignmentId === assignment.id;
                      
                      // Load submissions if not already loaded
                      if (assignmentSubmissions[assignment.id] === undefined && !loadingSubmissions[assignment.id]) {
                        loadSubmissions(assignment.id);
                      }
                      
                      return (
                        <div 
                          key={assignment.id} 
                          style={{
                            marginBottom: '20px',
                            padding: '20px',
                            background: '#f9f9f9',
                            borderRadius: '8px',
                            border: '1px solid #e0e0e0'
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                            <div style={{ flex: 1 }}>
                              <h4 style={{ margin: '0 0 10px 0', color: '#333' }}>
                                {assignment.topic}
                              </h4>
                              <p style={{ margin: '5px 0', color: '#666', fontSize: '14px' }}>
                                <strong>Description:</strong> {assignment.description}
                              </p>
                              <div style={{ marginTop: '10px', fontSize: '13px', color: '#666' }}>
                                <span><strong>Submissions:</strong> {loadingSubmissions[assignment.id] ? 'Loading...' : submissions.length}</span>
                                {submissions.some((s: any) => s.grade != null) && (
                                  <span style={{ marginLeft: '15px', color: '#48bb78', fontWeight: 'bold' }}>
                                    ✓ Graded
                                  </span>
                                )}
                              </div>
                            </div>
                            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                              <button
                                onClick={() => handleGradeAssignment(assignment.id)}
                                disabled={!hasSubmissions || isGrading || loadingSubmissions[assignment.id]}
                                style={{
                                  padding: '10px 20px',
                                  background: hasSubmissions && !isGrading && !loadingSubmissions[assignment.id] ? '#48bb78' : '#cbd5e0',
                                  color: 'white',
                                  border: 'none',
                                  borderRadius: '6px',
                                  cursor: hasSubmissions && !isGrading && !loadingSubmissions[assignment.id] ? 'pointer' : 'not-allowed',
                                  fontWeight: 'bold',
                                  whiteSpace: 'nowrap'
                                }}
                              >
                                {isCurrentlyGrading ? 'Grading...' : hasSubmissions ? 'Grade All' : 'No Submissions'}
                              </button>
                              <button
                                onClick={() => handleExportGrades(assignment.id)}
                                disabled={!hasSubmissions || loadingSubmissions[assignment.id]}
                                style={{
                                  padding: '10px 20px',
                                  background: hasSubmissions && !loadingSubmissions[assignment.id] ? '#4299e1' : '#cbd5e0',
                                  color: 'white',
                                  border: 'none',
                                  borderRadius: '6px',
                                  cursor: hasSubmissions && !loadingSubmissions[assignment.id] ? 'pointer' : 'not-allowed',
                                  fontWeight: 'bold',
                                  whiteSpace: 'nowrap'
                                }}
                                title="Export grades to CSV"
                              >
                                📥 Export CSV
                              </button>
                            </div>
                          </div>
                          
                          {hasSubmissions && (
                            <details style={{ marginTop: '15px' }}>
                              <summary style={{ cursor: 'pointer', color: '#4299e1', fontWeight: 'bold' }}>
                                View Submissions ({submissions.length})
                              </summary>
                              <div style={{ marginTop: '10px', paddingLeft: '15px' }}>
                                {submissions.map((submission: any, idx: number) => (
                                  <div 
                                    key={submission.id}
                                    style={{
                                      marginBottom: '10px',
                                      padding: '12px',
                                      background: 'white',
                                      borderRadius: '5px',
                                      border: '1px solid #e0e0e0'
                                    }}
                                  >
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                                      <strong style={{ color: '#2d3748' }}>Submission #{idx + 1}</strong>
                                      {submission.grade != null && (
                                        <span style={{ 
                                          padding: '4px 12px',
                                          background: '#c6f6d5',
                                          color: '#22543d',
                                          borderRadius: '12px',
                                          fontSize: '14px',
                                          fontWeight: 'bold'
                                        }}>
                                          Grade: {submission.grade}%
                                        </span>
                                      )}
                                    </div>
                                    <div style={{ fontSize: '14px', color: '#666', lineHeight: '1.8' }}>
                                      <div><strong>Roll Number:</strong> {submission.roll_number}</div>
                                      {submission.plagiarism_score != null && (
                                        <div><strong>Plagiarism Score:</strong> {submission.plagiarism_score}%</div>
                                      )}
                                      {submission.grade_reason && (
                                        <div style={{ marginTop: '8px' }}>
                                          <strong>Grade Reason:</strong>
                                          <div style={{ 
                                            marginTop: '5px',
                                            padding: '8px',
                                            background: '#f5f5f5',
                                            borderRadius: '4px',
                                            whiteSpace: 'pre-wrap',
                                            fontSize: '13px'
                                          }}>
                                            {submission.grade_reason}
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </details>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Submission Details Modal */}
          {showSubmissionModal && selectedSubmission && (
            <div className="modal-overlay" onClick={() => setShowSubmissionModal(false)}>
              <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '900px', maxHeight: '90vh', overflow: 'auto' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                  <h2>Submission Details</h2>
                  <button 
                    className="close-button"
                    onClick={() => setShowSubmissionModal(false)}
                    style={{ fontSize: '24px', background: 'none', border: 'none', cursor: 'pointer' }}
                  >
                    ×
                  </button>
                </div>

                <div style={{ padding: '20px' }}>
                  <div style={{ marginBottom: '20px' }}>
                    <h3 style={{ marginBottom: '10px' }}>{selectedSubmission.assignments?.topic || 'Assignment'}</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      <div>
                        <strong>Student Name:</strong> {selectedSubmission.profiles?.name || 'N/A'}
                      </div>
                      <div>
                        <strong>Roll Number:</strong> {selectedSubmission.roll_number || 'N/A'}
                      </div>
                      <div>
                        <strong>Submitted At:</strong> {selectedSubmission.submitted_at ? new Date(selectedSubmission.submitted_at).toLocaleString() : 'N/A'}
                      </div>
                      {selectedSubmission.grade !== null && selectedSubmission.grade !== undefined && (
                        <div>
                          <strong>Grade:</strong> {selectedSubmission.grade} / {selectedSubmission.assignments?.rubric?.total_points || 'N/A'}
                        </div>
                      )}
                      {selectedSubmission.plagiarism_score !== null && selectedSubmission.plagiarism_score !== undefined && (
                        <div>
                          <strong>Plagiarism Score:</strong> {selectedSubmission.plagiarism_score}%
                        </div>
                      )}
                      {selectedSubmission.grade_reason && (
                        <div>
                          <strong>Feedback:</strong>
                          <div style={{ marginTop: '5px', padding: '10px', background: '#f7fafc', borderRadius: '4px' }}>
                            {selectedSubmission.grade_reason}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {selectedSubmission.file_url && (
                    <div style={{ marginBottom: '20px' }}>
                      <strong>Submitted File:</strong>
                      <div style={{ marginTop: '10px' }}>
                        <a 
                          href={selectedSubmission.file_url} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          style={{ 
                            display: 'inline-block',
                            padding: '10px 20px',
                            backgroundColor: '#3182ce',
                            color: 'white',
                            textDecoration: 'none',
                            borderRadius: '4px',
                            fontWeight: 'bold'
                          }}
                        >
                          📄 Download File ({selectedSubmission.file_name || 'submission'})
                        </a>
                      </div>
                    </div>
                  )}

                  {selectedSubmission.answer_text && (
                    <div style={{ marginBottom: '20px' }}>
                      <strong>Answer Text:</strong>
                      <div style={{ marginTop: '10px', padding: '15px', background: '#f7fafc', borderRadius: '4px', whiteSpace: 'pre-wrap', maxHeight: '400px', overflowY: 'auto' }}>
                        {selectedSubmission.answer_text}
                      </div>
                    </div>
                  )}

                  {selectedSubmission.web_sources && selectedSubmission.web_sources.length > 0 && (
                    <div style={{ marginBottom: '20px' }}>
                      <strong>Web Sources:</strong>
                      <ul style={{ marginTop: '10px', paddingLeft: '20px' }}>
                        {selectedSubmission.web_sources.map((source: any, index: number) => (
                          <li key={index} style={{ marginBottom: '5px' }}>
                            <a href={source.url} target="_blank" rel="noopener noreferrer" style={{ color: '#3182ce' }}>
                              {source.title || source.url}
                            </a>
                            {source.similarity && <span style={{ color: '#666', marginLeft: '10px' }}>({source.similarity.toFixed(1)}% similar)</span>}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {selectedSubmission.academic_sources && selectedSubmission.academic_sources.length > 0 && (
                    <div style={{ marginBottom: '20px' }}>
                      <strong>Academic Sources:</strong>
                      <ul style={{ marginTop: '10px', paddingLeft: '20px' }}>
                        {selectedSubmission.academic_sources.map((source: any, index: number) => (
                          <li key={index} style={{ marginBottom: '5px' }}>
                            <a href={source.url} target="_blank" rel="noopener noreferrer" style={{ color: '#3182ce' }}>
                              {source.title || source.url}
                            </a>
                            {source.similarity && <span style={{ color: '#666', marginLeft: '10px' }}>({source.similarity.toFixed(1)}% similar)</span>}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Edit Assignment Modal */}
          {showEditModal && editingAssignment && (
            <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
              <div className="modal-content" style={{ maxWidth: '800px', maxHeight: '90vh', overflowY: 'auto' }} onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                  <h3>Edit Assignment</h3>
                  <button 
                    className="close-button"
                    onClick={() => setShowEditModal(false)}
                  >
                    ×
                  </button>
                </div>

                <form onSubmit={async (e) => {
                  e.preventDefault();
                  try {
                    setIsSubmitting(true);
                    await apiService.updateAssignment(editingAssignment.id, {
                      topic: editForm.topic,
                      description: editForm.description,
                      type: editForm.type,
                      num_questions: editForm.num_questions,
                      section: '', // Optional - not used in class-based system
                      deadline: editForm.deadline || undefined
                    });
                    showToast('✓ Assignment updated successfully', 'success');
                    setShowEditModal(false);
                    setEditingAssignment(null);
                    loadAssignments();
                  } catch (error: any) {
                    showToast(error.message || 'Failed to update assignment', 'error');
                  } finally {
                    setIsSubmitting(false);
                  }
                }}>
                  <div className="form-group">
                    <label htmlFor="edit-topic">Assignment Topic *</label>
                    <input
                      type="text"
                      id="edit-topic"
                      name="topic"
                      value={editForm.topic}
                      onChange={(e) => setEditForm(prev => ({ ...prev, topic: e.target.value }))}
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="edit-description">Description *</label>
                    <textarea
                      id="edit-description"
                      name="description"
                      value={editForm.description}
                      onChange={(e) => setEditForm(prev => ({ ...prev, description: e.target.value }))}
                      rows={4}
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="edit-type">Type *</label>
                    <select
                      id="edit-type"
                      name="type"
                      value={editForm.type}
                      onChange={(e) => setEditForm(prev => ({ ...prev, type: e.target.value }))}
                      required
                    >
                      <option value="theoretical">Theoretical</option>
                      <option value="coding">Coding</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label htmlFor="edit-num-questions">Number of Questions *</label>
                    <input
                      type="number"
                      id="edit-num-questions"
                      name="num_questions"
                      value={editForm.num_questions}
                      onChange={(e) => setEditForm(prev => ({ ...prev, num_questions: parseInt(e.target.value) || 5 }))}
                      min="1"
                      max="50"
                      required
                    />
                  </div>


                  <div className="form-group">
                    <label htmlFor="edit-deadline">Deadline (Optional)</label>
                    <input
                      type="datetime-local"
                      id="edit-deadline"
                      name="deadline"
                      value={editForm.deadline}
                      onChange={(e) => setEditForm(prev => ({ ...prev, deadline: e.target.value }))}
                    />
                  </div>

                  <div style={{ marginTop: '20px', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                    <button
                      type="button"
                      onClick={() => setShowEditModal(false)}
                      disabled={isSubmitting}
                      style={{
                        padding: '10px 20px',
                        backgroundColor: '#e0e0e0',
                        color: '#333',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: isSubmitting ? 'not-allowed' : 'pointer'
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isSubmitting}
                      style={{
                        padding: '10px 20px',
                        backgroundColor: isSubmitting ? '#999' : '#3182ce',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: isSubmitting ? 'not-allowed' : 'pointer',
                        fontWeight: 'bold'
                      }}
                    >
                      {isSubmitting ? 'Updating...' : 'Update Assignment'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* Create Class Modal */}
          {showCreateClassModal && (
            <div className="modal-overlay" onClick={() => setShowCreateClassModal(false)}>
              <div className="modal-content" style={{ maxWidth: '600px' }} onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                  <h3>Create New Class</h3>
                  <button 
                    className="close-button"
                    onClick={() => setShowCreateClassModal(false)}
                  >
                    ×
                  </button>
                </div>

                <form onSubmit={async (e) => {
                  e.preventDefault();
                  try {
                    setIsSubmitting(true);
                    const result = await apiService.createClass({
                      name: classForm.name,
                      code: classForm.code || undefined,
                      description: classForm.description || undefined
                    });
                    if (result.success) {
                      showToast('✓ Class created successfully!', 'success');
                      setShowCreateClassModal(false);
                      setClassForm({ name: '', code: '', description: '' });
                      await loadClasses();
                      if (result.class_id) {
                        setSelectedClassId(result.class_id);
                      }
                    }
                  } catch (error: any) {
                    showToast(error.message || 'Failed to create class', 'error');
                  } finally {
                    setIsSubmitting(false);
                  }
                }}>
                  <div className="form-group">
                    <label htmlFor="class-name">Class Name *</label>
                    <input
                      type="text"
                      id="class-name"
                      value={classForm.name}
                      onChange={(e) => setClassForm(prev => ({ ...prev, name: e.target.value }))}
                      required
                      placeholder="e.g., Mathematics, Science, English"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="class-code">Class Code (Optional)</label>
                    <input
                      type="text"
                      id="class-code"
                      value={classForm.code}
                      onChange={(e) => setClassForm(prev => ({ ...prev, code: e.target.value }))}
                      placeholder="e.g., MATH-101, CS-201"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="class-description">Description (Optional)</label>
                    <textarea
                      id="class-description"
                      value={classForm.description}
                      onChange={(e) => setClassForm(prev => ({ ...prev, description: e.target.value }))}
                      rows={3}
                      placeholder="Brief description of the class"
                    />
                  </div>

                  <div style={{ marginTop: '20px', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                    <button
                      type="button"
                      onClick={() => setShowCreateClassModal(false)}
                      disabled={isSubmitting}
                      style={{
                        padding: '10px 20px',
                        backgroundColor: '#e0e0e0',
                        color: '#333',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: isSubmitting ? 'not-allowed' : 'pointer'
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isSubmitting}
                      style={{
                        padding: '10px 20px',
                        backgroundColor: isSubmitting ? '#999' : '#4299e1',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: isSubmitting ? 'not-allowed' : 'pointer',
                        fontWeight: 'bold'
                      }}
                    >
                      {isSubmitting ? 'Creating...' : 'Create Class'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* Class Students Modal */}
          {showClassStudents && (
            <div className="modal-overlay" onClick={() => setShowClassStudents(false)}>
              <div className="modal-content" style={{ maxWidth: '700px', maxHeight: '80vh', overflow: 'auto' }} onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                  <h3>Students in Class</h3>
                  <button 
                    className="close-button"
                    onClick={() => setShowClassStudents(false)}
                  >
                    ×
                  </button>
                </div>

                <div style={{ padding: '20px' }}>
                  {classStudents.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#666' }}>
                      <p>No students enrolled in this class yet.</p>
                      <p style={{ fontSize: '14px', marginTop: '10px' }}>Enroll students using the enroll endpoint or admin panel.</p>
                    </div>
                  ) : (
                    <div>
                      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ background: '#f7fafc', borderBottom: '2px solid #e2e8f0' }}>
                            <th style={{ padding: '12px', textAlign: 'left' }}>Name</th>
                            <th style={{ padding: '12px', textAlign: 'left' }}>Email</th>
                            <th style={{ padding: '12px', textAlign: 'left' }}>Roll Number</th>
                          </tr>
                        </thead>
                        <tbody>
                          {classStudents.map((student: any) => (
                            <tr key={student.id} style={{ borderBottom: '1px solid #e2e8f0' }}>
                              <td style={{ padding: '12px' }}>{student.name}</td>
                              <td style={{ padding: '12px' }}>{student.email}</td>
                              <td style={{ padding: '12px' }}>{student.roll_number || 'N/A'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
        )}
      </main>
      {showSettings && <Settings onClose={() => setShowSettings(false)} />}
    </div>
  );
};

export default TeacherDashboard;
