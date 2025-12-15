import React, { useState, useEffect } from 'react';
import { supabase } from '../services/supabase';
import { apiService, createDevToken } from '../services/api';
import { useToast } from '../hooks/useToast';
import Toast from './Toast';
import Settings from './Settings';
import './Dashboard.css';
import './CommonStyles.css';

interface Rubric {
  total_points: number;
  criteria: string[];
}

interface Assignment {
  id: string;
  topic: string;
  description: string;
  type: string;
  num_questions: number;
  questions: string[];
  rubric: Rubric;
  deadline: string | null;
  published: boolean;
}

interface Submission {
  roll_number: string;
  assignment_number: string;
  file: File | null;
  answer_text: string;
}

interface StudentDashboardProps {
  user: any;
  profile: any;
  onSignOut: () => void;
}

const StudentDashboard: React.FC<StudentDashboardProps> = ({ user, profile, onSignOut }) => {
  const { toasts, showToast, removeToast } = useToast();
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedAssignment, setSelectedAssignment] = useState<Assignment | null>(null);
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [submittingAssignment, setSubmittingAssignment] = useState<Assignment | null>(null);
  const [submissionForm, setSubmissionForm] = useState<Submission>({
    roll_number: '',
    assignment_number: '',
    file: null,
    answer_text: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submittedAssignments, setSubmittedAssignments] = useState<Set<string>>(new Set());
  const [submissionDetails, setSubmissionDetails] = useState<any>(null);
  const [showSubmissionModal, setShowSubmissionModal] = useState(false);
  const [classes, setClasses] = useState<any[]>([]);
  const [selectedClassId, setSelectedClassId] = useState<string | null>(null);
  const [showEnrollModal, setShowEnrollModal] = useState(false);
  const [enrollCode, setEnrollCode] = useState('');
  const [isEnrolling, setIsEnrolling] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    // Set up auth token on mount
    if (user && profile) {
      const token = createDevToken(user.id, user.email, profile.role, profile.name);
      localStorage.setItem('auth_token', token);
    }
    loadClasses();
  }, []);

  useEffect(() => {
    if (selectedClassId || classes.length > 0) {
      fetchAssignments();
    }
  }, [selectedClassId]);

  const loadClasses = async () => {
    try {
      const result = await apiService.getMyClasses();
      if (result.success && result.classes) {
        setClasses(result.classes);
        // Auto-select first class if available
        if (result.classes.length > 0 && !selectedClassId) {
          setSelectedClassId(result.classes[0].id);
        } else if (result.classes.length === 0) {
          // If no classes, still try to fetch assignments (legacy mode)
          fetchAssignments();
        }
      }
    } catch (error: any) {
      console.error('Error loading classes:', error);
      // Fallback to legacy assignment fetching
      fetchAssignments();
    }
  };

  const fetchSubmittedAssignments = async () => {
    try {
      console.log('Fetching submitted assignments for student:', user.id);
      
      // Use Supabase directly for submissions (RLS will filter by student_id)
      const { data, error } = await supabase
        .from('submissions')
        .select('assignment_id')
        .eq('student_id', user.id);

      console.log('Submitted assignments query result:', { data, error });

      if (error) {
        console.error('Error fetching submitted assignments:', error);
        return;
      }

      if (data) {
        console.log('Found submitted assignments:', data);
        const submittedIds = new Set(data.map(s => s.assignment_id));
        console.log('Submitted IDs Set:', submittedIds);
        setSubmittedAssignments(submittedIds);
      }
    } catch (error) {
      console.error('Error fetching submitted assignments:', error);
    }
  };

  const fetchAssignments = async () => {
    try {
      console.log('Student fetching assignments via RBAC API...');
      
      // Use RBAC API endpoint which filters by role and only returns published assignments from student's teacher
      // Pass selectedClassId to filter assignments by class
      const result = await apiService.getMyAssignments(selectedClassId || undefined);
      
      console.log('Student assignments result:', result);

      if (result.success && result.assignments) {
        // Backend already filters by published=True and teacher, but double-check for safety
        const publishedAssignments = result.assignments.filter((a: any) => a.published === true);
        
        // Update submittedAssignments set from the is_submitted field in each assignment
        const submittedIds = new Set<string>();
        publishedAssignments.forEach((a: any) => {
          if (a.is_submitted) {
            submittedIds.add(a.id);
          }
        });
        setSubmittedAssignments(submittedIds);
        console.log('Updated submitted assignments from API:', submittedIds);
        console.log(`✓ Found ${publishedAssignments.length} published assignments from teacher`);
        setAssignments(publishedAssignments);
        
        if (publishedAssignments.length === 0) {
          showToast('No published assignments available from your teacher', 'info');
        }
      } else {
        setAssignments([]);
        showToast('No assignments available', 'info');
      }
    } catch (error: any) {
      console.error('Error fetching assignments:', error);
      showToast(error.message || 'Failed to fetch assignments', 'error');
      setAssignments([]);
    } finally {
      setIsLoading(false);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  };

  const formatDateTime = (dateString: string) => {
    return new Date(dateString).toLocaleString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const isOverdue = (dueDate: string | null) => {
    if (!dueDate) return false;
    return new Date(dueDate) < new Date();
  };

  const isDeadlinePassed = (dueDate: string | null) => {
    if (!dueDate) return false;
    const now = new Date();
    const deadline = new Date(dueDate);
    // Use the actual time from the deadline, don't override it
    return now > deadline;
  };

  const fetchSubmissionDetails = async (assignmentId: string) => {
    try {
      const response = await fetch(`${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/get-my-submissions?assignment_id=${assignmentId}`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch submission details');
      }

      const result = await response.json();
      if (result.success && result.submissions && result.submissions.length > 0) {
        setSubmissionDetails(result.submissions[0]);
        setShowSubmissionModal(true);
      } else {
        showToast('No submission found for this assignment', 'info');
      }
    } catch (error: any) {
      console.error('Error fetching submission details:', error);
      showToast(error.message || 'Failed to fetch submission details', 'error');
    }
  };

  const openSubmitModal = (assignment: Assignment) => {
    // Check if deadline has passed
    if (isDeadlinePassed(assignment.deadline)) {
      showToast('Submission deadline has passed. You can no longer submit this assignment.', 'error');
      return;
    }
    setSubmittingAssignment(assignment);
    
    setSubmissionForm({
      roll_number: profile?.roll_number || '',
      assignment_number: assignment.id.substring(0, 8), // First 8 chars of UUID as assignment number
      file: null,
      answer_text: ''
    });
    setShowSubmitModal(true);
  };

  const handleUnsubmitAssignment = async (assignmentId: string) => {
    if (!window.confirm('Are you sure you want to unsubmit this assignment? You will be able to submit again after unsubmitting.')) {
      return;
    }

    try {
      setIsSubmitting(true);
      showToast('Unsubmitting assignment...', 'info');
      
      await apiService.unsubmitAssignment(assignmentId);
      
      // Remove from submitted assignments set
      setSubmittedAssignments(prev => {
        const newSet = new Set(prev);
        newSet.delete(assignmentId);
        return newSet;
      });
      
      showToast('✓ Assignment unsubmitted successfully! You can now submit again.', 'success');
    } catch (error: any) {
      console.error('Error unsubmitting assignment:', error);
      showToast(error.message || 'Failed to unsubmit assignment', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmissionFormChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setSubmissionForm(prev => ({ ...prev, [name]: value }));
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    if (file) {
      // Check file type
      const allowedTypes = ['.py', '.cpp', '.pdf', '.doc', '.docx', '.txt'];
      const fileExt = '.' + file.name.split('.').pop()?.toLowerCase();
      
      if (!allowedTypes.includes(fileExt)) {
        showToast('Only .py, .cpp, .pdf, .doc, .docx, or .txt files allowed', 'warning');
        e.target.value = '';
        return;
      }

      // Check file size (max 10MB)
      if (file.size > 10 * 1024 * 1024) {
        showToast('File size must be less than 10MB', 'warning');
        e.target.value = '';
        return;
      }

      setSubmissionForm(prev => ({ ...prev, file }));
    }
  };

  const handleSubmitAssignment = async () => {
    if (!submittingAssignment) {
      console.error('No assignment selected for submission');
      return;
    }

    console.log('Starting submission process...');
    console.log('Form data:', submissionForm);
    console.log('User:', user);

    // Validation - Roll number is auto-filled from profile
    if (!submissionForm.roll_number || !submissionForm.roll_number.trim()) {
      showToast('Roll number is missing. Please update your profile with a roll number.', 'warning');
      return;
    }
    if (!submissionForm.file && !submissionForm.answer_text.trim()) {
      showToast('Please upload a file or enter answer text', 'warning');
      return;
    }

    setIsSubmitting(true);

    try {
      let fileUrl = null;
      let fileName = null;

      // Upload file to Supabase storage if provided
      if (submissionForm.file) {
        const fileExt = submissionForm.file.name.split('.').pop();
        
        // Format: name_rollnum_assignmentnumber
        // Sanitize name: remove spaces and special characters, keep only alphanumeric and underscores
        const sanitizedName = (profile?.name || 'student')
          .replace(/[^a-zA-Z0-9_]/g, '_')
          .replace(/_+/g, '_')
          .toLowerCase();
        
        const rollNumber = submissionForm.roll_number.replace(/[^a-zA-Z0-9_]/g, '_');
        const assignmentNumber = submissionForm.assignment_number || submittingAssignment.id.substring(0, 8);
        
        const uniqueFileName = `${sanitizedName}_${rollNumber}_${assignmentNumber}.${fileExt}`;
        
        console.log('Attempting to upload file:', uniqueFileName);
        console.log('File object:', submissionForm.file);

        // Pre-check bucket availability (optional - listBuckets might not have permissions)
        // We'll try the upload directly and handle errors there
        try {
          const { data: buckets, error: bucketListError } = await supabase.storage.listBuckets();
          console.log('Pre-upload bucket check:', { buckets, bucketListError });
          
          if (bucketListError) {
            console.warn('Cannot list buckets (permission issue), but will try upload anyway:', bucketListError);
            // Don't fail here - listBuckets might not be allowed but upload might work
          } else if (buckets) {
            const targetBucket = buckets.find((b: any) => b.name === 'assignment-submissions');
            if (targetBucket) {
              console.log('✓ Bucket found:', targetBucket);
              if (!targetBucket.public) {
                showToast(
                  'Storage bucket "assignment-submissions" exists but is PRIVATE. Please make it PUBLIC in Supabase Storage settings.',
                  'error'
                );
                setIsSubmitting(false);
                return;
              }
            } else {
              console.warn('Bucket not found in list, but will try upload anyway (listBuckets might not show all buckets)');
            }
          }
        } catch (preCheckError) {
          console.warn('Pre-check failed, proceeding with upload attempt:', preCheckError);
          // Don't fail - just log and continue
        }

        try {
          const { data: uploadData, error: uploadError } = await supabase.storage
            .from('assignment-submissions')
            .upload(uniqueFileName, submissionForm.file, {
              cacheControl: '3600',
              upsert: false
            });

          if (uploadError) {
            console.error('File upload error:', uploadError);
            console.error('Upload error details:', JSON.stringify(uploadError, null, 2));
            
            // Provide helpful error message based on the actual upload error
            let errorMessage = 'Failed to upload file. ';
            const errorMsg = uploadError.message || '';
            
            // Try to get bucket info (but don't fail if listBuckets doesn't work)
            let buckets: any[] | null = null;
            let targetBucket: any = null;
            try {
              const { data: bucketData, error: bucketError } = await supabase.storage.listBuckets();
              if (!bucketError && bucketData) {
                buckets = bucketData;
                targetBucket = bucketData.find((b: any) => b.name === 'assignment-submissions');
                console.log('Available buckets:', bucketData.map((b: any) => b.name).join(', '));
                console.log('Target bucket:', targetBucket);
              } else {
                console.warn('Cannot list buckets (may not have permission):', bucketError);
              }
            } catch (e) {
              console.warn('Error listing buckets:', e);
            }
            
            if (errorMsg.includes('Bucket not found') || errorMsg.includes('not found') || errorMsg.includes('does not exist') || errorMsg.includes('404')) {
              if (targetBucket) {
                errorMessage += 'Bucket exists but upload failed. ';
                errorMessage += `Bucket is ${targetBucket.public ? 'public' : 'PRIVATE'}. `;
                if (!targetBucket.public) {
                  errorMessage += 'Please make it PUBLIC in Supabase Storage settings.';
                } else {
                  errorMessage += 'Check Storage Policies - you need an INSERT policy.';
                }
              } else {
                errorMessage += 'Storage bucket "assignment-submissions" not found. ';
                errorMessage += 'Verify: 1) Bucket exists in Supabase, 2) Name is exactly "assignment-submissions", 3) Using correct Supabase project.';
                if (buckets && buckets.length > 0) {
                  errorMessage += ` Available buckets: ${buckets.map((b: any) => b.name).join(', ')}.`;
                }
              }
            } else if (errorMsg.includes('new row violates row-level security') || errorMsg.includes('RLS') || errorMsg.includes('permission denied') || errorMsg.includes('policy') || errorMsg.includes('unauthorized') || errorMsg.includes('403') || errorMsg.includes('Forbidden')) {
              errorMessage += 'Permission denied. Storage Policies are blocking the upload. ';
              errorMessage += 'Go to Supabase → Storage → assignment-submissions → Policies → Create INSERT policy. ';
              errorMessage += 'See STORAGE_POLICY_SETUP.md for instructions.';
            } else if (errorMsg.includes('413') || errorMsg.includes('too large') || errorMsg.includes('File size')) {
              errorMessage += 'File is too large. Maximum size is 50 MB.';
            } else {
              errorMessage += `Error: ${errorMsg}. `;
              errorMessage += 'Check browser console (F12) for full error details.';
            }
            
            // Add specific error code if available
            const errorCode = (uploadError as any).statusCode || (uploadError as any).status;
            if (errorCode) {
              errorMessage += ` (Error code: ${errorCode})`;
            }
            
            console.error('Upload error details:', { 
              buckets: buckets?.map((b: any) => b.name) || 'could not list',
              targetBucket: targetBucket ? { name: targetBucket.name, public: targetBucket.public } : 'not found',
              uploadError: {
                message: uploadError.message,
                name: uploadError.name,
                ...(errorCode && { statusCode: errorCode })
              }
            });
            showToast(errorMessage, 'error');
            setIsSubmitting(false);
            return;
          }

          console.log('Upload successful:', uploadData);

          // Get public URL
          const { data: urlData } = supabase.storage
            .from('assignment-submissions')
            .getPublicUrl(uniqueFileName);

          fileUrl = urlData.publicUrl;
          fileName = submissionForm.file.name;

          console.log('File uploaded successfully. Public URL:', fileUrl);
        } catch (uploadErr) {
          console.error('Upload exception:', uploadErr);
          showToast('File upload failed', 'error');
          setIsSubmitting(false);
          return;
        }
      }

      // Save submission using RBAC API
      console.log('Saving submission via RBAC API...');
      
      try {
        const result = await apiService.submitAssignment({
          assignment_id: submittingAssignment.id,
          roll_number: submissionForm.roll_number,
          section: '', // Optional - not used in class-based system
          file_url: fileUrl || undefined,
          answer_text: submissionForm.answer_text || undefined
        });

        if (!result.success) {
          throw new Error(result.message || 'Failed to submit assignment');
        }

        console.log('Submission saved successfully:', result);
        // Add to submitted assignments IMMEDIATELY
        setSubmittedAssignments(prev => {
          const newSet = new Set(prev);
          newSet.add(submittingAssignment.id);
          return newSet;
        });

        // Reset form and close modal
        setShowSubmitModal(false);
        setSubmittingAssignment(null);
        setSubmissionForm({
          roll_number: '',
          assignment_number: '',
          file: null,
          answer_text: ''
        });
        
        showToast('✓ Assignment submitted successfully!', 'success');
      } catch (apiError: any) {
        console.error('API submission error:', apiError);
        showToast(apiError.message || 'Failed to submit assignment', 'error');
        throw apiError; // Re-throw to be caught by outer catch
      }
    } catch (error: any) {
      console.error('Submission error:', error);
      showToast(error.message || 'An error occurred during submission', 'error');
    } finally {
      setIsSubmitting(false);
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
        <div className="dashboard-content">
          {/* Class Selection */}
          <div style={{ marginBottom: '20px', padding: '15px', background: '#f0f4ff', borderRadius: '8px', border: '1px solid #cbd5e0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <h3 style={{ margin: 0 }}>My Classes</h3>
              <button
                onClick={() => setShowEnrollModal(true)}
                style={{
                  padding: '8px 16px',
                  background: '#48bb78',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontWeight: 'bold',
                  fontSize: '14px'
                }}
              >
                + Enroll in Class
              </button>
            </div>
            {classes.length === 0 ? (
              <div style={{ padding: '20px', textAlign: 'center', background: '#fff3cd', borderRadius: '6px' }}>
                <p style={{ margin: '0 0 15px 0' }}>You're not enrolled in any classes yet.</p>
                <button
                  onClick={() => setShowEnrollModal(true)}
                  style={{
                    padding: '10px 20px',
                    background: '#48bb78',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontWeight: 'bold'
                  }}
                >
                  + Enroll Using Class Code
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                <button
                  onClick={() => {
                    setSelectedClassId(null);
                    fetchAssignments();
                  }}
                  style={{
                    padding: '10px 20px',
                    background: selectedClassId === null ? '#4299e1' : '#e2e8f0',
                    color: selectedClassId === null ? 'white' : '#2d3748',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontWeight: selectedClassId === null ? 'bold' : 'normal'
                  }}
                >
                  All Classes
                </button>
                {classes.map((cls) => (
                  <button
                    key={cls.id}
                    onClick={() => setSelectedClassId(cls.id)}
                    style={{
                      padding: '10px 20px',
                      background: selectedClassId === cls.id ? '#4299e1' : '#e2e8f0',
                      color: selectedClassId === cls.id ? 'white' : '#2d3748',
                      border: 'none',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: selectedClassId === cls.id ? 'bold' : 'normal'
                    }}
                  >
                    {cls.name} {cls.code && `(${cls.code})`}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="section-header">
            <h2>Your Assignments{selectedClassId && classes.find(c => c.id === selectedClassId) ? ` - ${classes.find(c => c.id === selectedClassId)?.name}` : ''}</h2>
            <p>View and submit your assignments</p>
          </div>

          {isLoading ? (
            <div className="loading">
              <div className="spinner"></div>
              <p>Loading assignments...</p>
            </div>
          ) : assignments.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📝</div>
              <h3>No assignments yet</h3>
              <p>Your teachers haven't uploaded any assignments yet.</p>
            </div>
          ) : (
            <div className="assignments-grid">
              {assignments.map((assignment) => {
                const isSubmitted = submittedAssignments.has(assignment.id);
                console.log(`Assignment ${assignment.topic} (${assignment.id}) - Submitted:`, isSubmitted);
                
                return (
                <div key={assignment.id} className="assignment-card">
                  <div className="assignment-header">
                    <div className="assignment-title-row">
                      <h3 className="assignment-title-large">{assignment.topic}</h3>
                      {isSubmitted && (
                        <span className="submitted-badge-small">
                          ✓ Submitted
                        </span>
                      )}
                    </div>
                    {assignment.deadline && (
                      <div className={`due-date-light ${isOverdue(assignment.deadline) ? 'overdue' : ''}`}>
                        Due: {formatDateTime(assignment.deadline)}
                      </div>
                    )}
                  </div>
                  
                  <div className="assignment-content">
                    <div className="assignment-meta">
                      <span className="points">
                        {assignment.rubric?.total_points ? `${assignment.rubric.total_points} Points` : `${assignment.num_questions} Questions`}
                      </span>
                      <span className="type">Type: {assignment.type}</span>
                    </div>
                  </div>

                  <div className="assignment-actions">
                    <button 
                      className="view-button"
                      onClick={() => setSelectedAssignment(assignment)}
                    >
                      View Questions & Rubric
                    </button>
                    {isSubmitted ? (
                      <>
                        <button 
                          className="view-submission-button"
                          onClick={() => fetchSubmissionDetails(assignment.id)}
                          style={{ 
                            marginTop: '10px', 
                            backgroundColor: '#3182ce', 
                            color: 'white',
                            cursor: 'pointer',
                            border: 'none',
                            padding: '10px 20px',
                            borderRadius: '6px',
                            fontWeight: 'bold'
                          }}
                        >
                          📄 View Submission
                        </button>
                        {!isDeadlinePassed(assignment.deadline) && (
                          <button 
                            className="unsubmit-button"
                            onClick={() => handleUnsubmitAssignment(assignment.id)}
                            disabled={isSubmitting}
                            style={{ 
                              marginTop: '10px', 
                              backgroundColor: '#e53e3e', 
                              color: 'white',
                              cursor: isSubmitting ? 'not-allowed' : 'pointer',
                              border: 'none',
                              padding: '10px 20px',
                              borderRadius: '6px',
                              fontWeight: 'bold'
                            }}
                          >
                            {isSubmitting ? 'Unsubmitting...' : '↩ Unsubmit'}
                          </button>
                        )}
                      </>
                    ) : (
                    <button 
                      className="submit-button"
                      onClick={() => openSubmitModal(assignment)}
                        disabled={isSubmitting || isDeadlinePassed(assignment.deadline)}
                      style={{ 
                        marginTop: '10px', 
                          backgroundColor: isDeadlinePassed(assignment.deadline) ? '#a0aec0' : '#48bb78', 
                        color: 'white',
                          cursor: (isSubmitting || isDeadlinePassed(assignment.deadline)) ? 'not-allowed' : 'pointer',
                          border: 'none',
                          padding: '10px 20px',
                          borderRadius: '6px',
                          fontWeight: 'bold'
                      }}
                    >
                        {isDeadlinePassed(assignment.deadline) ? '⏰ Deadline Passed' : 'Submit Assignment'}
                    </button>
                    )}
                  </div>
                </div>
              );
              })}
            </div>
          )}

          {selectedAssignment && (
            <div className="modal-overlay" onClick={() => setSelectedAssignment(null)}>
              <div className="modal-content" style={{ maxWidth: '800px', maxHeight: '90vh', overflowY: 'auto' }} onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                  <h3>{selectedAssignment.topic}</h3>
                  <button 
                    className="close-button"
                    onClick={() => setSelectedAssignment(null)}
                  >
                    ×
                  </button>
                </div>

                <div style={{ padding: '20px' }}>
                  <div style={{ marginBottom: '20px', display: 'flex', gap: '15px', fontSize: '14px', flexWrap: 'wrap' }}>
                    <span><strong>Type:</strong> {selectedAssignment.type}</span>
                    <span><strong>Questions:</strong> {selectedAssignment.num_questions}</span>
                    {selectedAssignment.deadline && (
                      <span><strong>Deadline:</strong> {formatDateTime(selectedAssignment.deadline)}</span>
                    )}
                    {selectedAssignment.rubric?.total_points && (
                      <span><strong>Total Points:</strong> {selectedAssignment.rubric.total_points}</span>
                    )}
                  </div>

                  <hr style={{ margin: '20px 0', border: 'none', borderTop: '1px solid #e0e0e0' }} />

                  <h4>Questions:</h4>
                  <div style={{ 
                    background: '#f5f5f5', 
                    padding: '15px', 
                    borderRadius: '8px',
                    marginTop: '10px'
                  }}>
                    {Array.isArray(selectedAssignment.questions) && selectedAssignment.questions.map((question: string, index: number) => (
                      <div key={index} style={{ 
                        marginBottom: '15px',
                        padding: '15px',
                        background: 'white',
                        borderRadius: '5px',
                        borderLeft: '3px solid #667eea'
                      }}>
                        <strong style={{ color: '#667eea' }}>Question {index + 1}:</strong>
                        <p style={{ marginTop: '8px', marginBottom: '0', lineHeight: '1.6' }}>{question}</p>
                      </div>
                    ))}
                  </div>

                  {selectedAssignment.rubric && selectedAssignment.rubric.total_points && (
                    <div style={{ marginTop: '20px' }}>
                      <h4>Grading Rubric:</h4>
                      <div style={{ 
                        background: '#f0f7ff', 
                        padding: '15px', 
                        borderRadius: '8px',
                        marginTop: '10px',
                        border: '1px solid #d0e7ff'
                      }}>
                        <div style={{ 
                          marginBottom: '15px',
                          padding: '12px',
                          background: 'white',
                          borderRadius: '5px',
                          borderLeft: '4px solid #4299e1',
                          fontSize: '16px',
                          fontWeight: 'bold',
                          color: '#2c5282'
                        }}>
                          Total Points: {selectedAssignment.rubric.total_points}
                        </div>
                        <div style={{ marginTop: '15px' }}>
                          <strong style={{ fontSize: '15px' }}>Grading Criteria:</strong>
                          <ul style={{ marginTop: '10px', paddingLeft: '25px', lineHeight: '1.8' }}>
                            {selectedAssignment.rubric.criteria.map((criterion: string, index: number) => (
                              <li key={index} style={{ marginBottom: '10px', color: '#2d3748' }}>
                                {criterion}
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </div>
                  )}

                  <div style={{ marginTop: '30px', padding: '15px', background: '#fff3cd', borderRadius: '8px', border: '1px solid #ffc107' }}>
                    <p style={{ margin: 0, color: '#856404' }}>
                      <strong>Note:</strong> Please review all questions and grading criteria carefully before submitting your work.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Submission Modal */}
          {showSubmitModal && submittingAssignment && (
            <div className="modal-overlay" onClick={() => !isSubmitting && setShowSubmitModal(false)}>
              <div className="modal-content" style={{ maxWidth: '600px' }} onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                  <h3>Submit Assignment: {submittingAssignment.topic}</h3>
                  <button 
                    className="close-button"
                    onClick={() => setShowSubmitModal(false)}
                    disabled={isSubmitting}
                  >
                    ×
                  </button>
                </div>

                <div style={{ padding: '20px' }}>
                  <div className="form-group">
                    <label htmlFor="roll_number">Roll Number</label>
                    <input
                      type="text"
                      id="roll_number"
                      name="roll_number"
                      value={submissionForm.roll_number || 'Not set in profile'}
                      disabled
                      style={{ backgroundColor: '#f5f5f5', cursor: 'not-allowed' }}
                    />
                    <small style={{ color: '#666', display: 'block', marginTop: '5px' }}>
                      Roll number from your profile (set during signup)
                    </small>
                  </div>

                  <div className="form-group">
                    <label htmlFor="assignment_number">Assignment Number</label>
                    <input
                      type="text"
                      id="assignment_number"
                      name="assignment_number"
                      value={submissionForm.assignment_number}
                      disabled
                      style={{ backgroundColor: '#f5f5f5', cursor: 'not-allowed' }}
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="file">Upload File (Optional)</label>
                    <input
                      type="file"
                      id="file"
                      name="file"
                      onChange={handleFileChange}
                      accept=".py,.cpp,.pdf,.doc,.docx,.txt"
                      disabled={isSubmitting}
                      style={{ padding: '8px' }}
                    />
                    <small style={{ color: '#666', display: 'block', marginTop: '5px' }}>
                      Accepted formats: .py, .cpp, .pdf, .doc, .docx, .txt (Max 10MB)
                    </small>
                    {submissionForm.file && (
                      <div style={{ 
                        marginTop: '10px', 
                        padding: '10px', 
                        background: '#e8f5e9', 
                        borderRadius: '4px',
                        color: '#2e7d32'
                      }}>
                        ✓ {submissionForm.file.name} ({(submissionForm.file.size / 1024).toFixed(2)} KB)
                      </div>
                    )}
                  </div>

                  <div className="form-group">
                    <label htmlFor="answer_text">Answer Text (Optional)</label>
                    <textarea
                      id="answer_text"
                      name="answer_text"
                      value={submissionForm.answer_text}
                      onChange={handleSubmissionFormChange}
                      placeholder="Enter your answers or additional notes here..."
                      rows={6}
                      disabled={isSubmitting}
                      style={{ resize: 'vertical', minHeight: '100px' }}
                    />
                    <small style={{ color: '#666', display: 'block', marginTop: '5px' }}>
                      You can either upload a file or type your answers here, or both.
                    </small>
                  </div>

                  <div style={{ marginTop: '20px', padding: '12px', background: '#fff3cd', borderRadius: '4px', border: '1px solid #ffc107' }}>
                    <p style={{ margin: 0, color: '#856404', fontSize: '14px' }}>
                      <strong>Note:</strong> Once submitted, you cannot modify your submission. Please review everything before submitting.
                    </p>
                  </div>

                  <div style={{ marginTop: '20px', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                    <button
                      onClick={() => setShowSubmitModal(false)}
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
                      onClick={handleSubmitAssignment}
                      disabled={isSubmitting}
                      style={{
                        padding: '10px 20px',
                        backgroundColor: isSubmitting ? '#999' : '#48bb78',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: isSubmitting ? 'not-allowed' : 'pointer',
                        fontWeight: 'bold'
                      }}
                    >
                      {isSubmitting ? 'Submitting...' : 'Submit Assignment'}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Submission Details Modal */}
          {showSubmissionModal && submissionDetails && (
            <div className="modal-overlay" onClick={() => setShowSubmissionModal(false)}>
              <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '800px', maxHeight: '90vh', overflow: 'auto' }}>
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
                    <h3 style={{ marginBottom: '10px' }}>{submissionDetails.assignments?.topic || 'Assignment'}</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      <div>
                        <strong>Submitted At:</strong> {submissionDetails.submitted_at ? new Date(submissionDetails.submitted_at).toLocaleString() : 'N/A'}
                      </div>
                      {submissionDetails.roll_number && (
                        <div>
                          <strong>Roll Number:</strong> {submissionDetails.roll_number}
                        </div>
                      )}
                      {submissionDetails.section && (
                        <div>
                          <strong>Section:</strong> {submissionDetails.section}
                        </div>
                      )}
                      {submissionDetails.grade !== null && submissionDetails.grade !== undefined && (
                        <div>
                          <strong>Grade:</strong> {submissionDetails.grade} / {submissionDetails.assignments?.rubric?.total_points || 'N/A'}
                        </div>
                      )}
                      {submissionDetails.plagiarism_score !== null && submissionDetails.plagiarism_score !== undefined && (
                        <div>
                          <strong>Plagiarism Score:</strong> {submissionDetails.plagiarism_score}%
                        </div>
                      )}
                      {submissionDetails.grade_reason && (
                        <div>
                          <strong>Feedback:</strong>
                          <div style={{ marginTop: '5px', padding: '10px', background: '#f7fafc', borderRadius: '4px' }}>
                            {submissionDetails.grade_reason}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {submissionDetails.file_url && (
                    <div style={{ marginBottom: '20px' }}>
                      <strong>Submitted File:</strong>
                      <div style={{ marginTop: '10px' }}>
                        <a 
                          href={submissionDetails.file_url} 
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
                          📄 Download File
                        </a>
                      </div>
                    </div>
                  )}

                  {submissionDetails.answer_text && (
                    <div style={{ marginBottom: '20px' }}>
                      <strong>Answer Text:</strong>
                      <div style={{ marginTop: '10px', padding: '15px', background: '#f7fafc', borderRadius: '4px', whiteSpace: 'pre-wrap' }}>
                        {submissionDetails.answer_text}
                      </div>
                    </div>
                  )}

                  {submissionDetails.web_sources && submissionDetails.web_sources.length > 0 && (
                    <div style={{ marginBottom: '20px' }}>
                      <strong>Web Sources:</strong>
                      <ul style={{ marginTop: '10px', paddingLeft: '20px' }}>
                        {submissionDetails.web_sources.map((source: any, index: number) => (
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

                  {submissionDetails.academic_sources && submissionDetails.academic_sources.length > 0 && (
                    <div style={{ marginBottom: '20px' }}>
                      <strong>Academic Sources:</strong>
                      <ul style={{ marginTop: '10px', paddingLeft: '20px' }}>
                        {submissionDetails.academic_sources.map((source: any, index: number) => (
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

          {/* Enroll in Class Modal */}
          {showEnrollModal && (
            <div className="modal-overlay" onClick={() => {
              setShowEnrollModal(false);
              setEnrollCode('');
            }}>
              <div className="modal-content" style={{ maxWidth: '500px' }} onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                  <h3>Enroll in Class</h3>
                  <button 
                    className="close-button"
                    onClick={() => {
                      setShowEnrollModal(false);
                      setEnrollCode('');
                    }}
                  >
                    ×
                  </button>
                </div>

                <form onSubmit={async (e) => {
                  e.preventDefault();
                  if (!enrollCode.trim()) {
                    showToast('Please enter a class code', 'warning');
                    return;
                  }
                  
                  try {
                    setIsEnrolling(true);
                    const result = await apiService.enrollByCode(enrollCode.trim());
                    if (result.success) {
                      showToast(`✓ ${result.message}`, 'success');
                      setShowEnrollModal(false);
                      setEnrollCode('');
                      // Reload classes
                      await loadClasses();
                      // Auto-select the newly enrolled class
                      if (result.class && result.class.id) {
                        setSelectedClassId(result.class.id);
                      }
                    }
                  } catch (error: any) {
                    showToast(error.message || 'Failed to enroll in class', 'error');
                  } finally {
                    setIsEnrolling(false);
                  }
                }}>
                  <div style={{ padding: '20px' }}>
                    <div className="form-group">
                      <label htmlFor="class-code">Class Code *</label>
                      <input
                        type="text"
                        id="class-code"
                        value={enrollCode}
                        onChange={(e) => setEnrollCode(e.target.value.toUpperCase())}
                        required
                        placeholder="e.g., MATH-101, CS-201"
                        style={{ textTransform: 'uppercase' }}
                        autoFocus
                      />
                      <p style={{ fontSize: '12px', color: '#666', marginTop: '5px' }}>
                        Enter the class code provided by your teacher
                      </p>
                    </div>

                    <div style={{ marginTop: '20px', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                      <button
                        type="button"
                        onClick={() => {
                          setShowEnrollModal(false);
                          setEnrollCode('');
                        }}
                        disabled={isEnrolling}
                        style={{
                          padding: '10px 20px',
                          backgroundColor: '#e0e0e0',
                          color: '#333',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: isEnrolling ? 'not-allowed' : 'pointer'
                        }}
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={isEnrolling}
                        style={{
                          padding: '10px 20px',
                          backgroundColor: isEnrolling ? '#999' : '#48bb78',
                          color: 'white',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: isEnrolling ? 'not-allowed' : 'pointer',
                          fontWeight: 'bold'
                        }}
                      >
                        {isEnrolling ? 'Enrolling...' : 'Enroll'}
                      </button>
                    </div>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      </main>
      {showSettings && <Settings onClose={() => setShowSettings(false)} />}
    </div>
  );
};

export default StudentDashboard;
