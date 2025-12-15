import React, { useState, useEffect } from 'react';
import { apiService } from '../services/api';
import './AnalyticsDashboard.css';

interface AssignmentAnalytics {
  assignment_id: string;
  topic: string;
  class_id: string | null;
  due_date: string | null;
  created_at: string;
  published: boolean;
  submission_rate: number;
  average_grade: number | null;
  late_submissions_pct: number;
  students_submitted: number;
  students_pending: number;
  total_students: number;
  graded_count: number;
  total_submissions: number;
}

interface AnalyticsData {
  success: boolean;
  assignments: AssignmentAnalytics[];
  total_students: number;
  total_assignments: number;
  overall_submission_rate?: number;
  overall_average_grade?: number | null;
  overall_late_pct?: number;
}

interface AnalyticsDashboardProps {
  classId?: string | null;
  onClose?: () => void;
}

const AnalyticsDashboard: React.FC<AnalyticsDashboardProps> = ({ classId = null, onClose }) => {
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedAssignment, setSelectedAssignment] = useState<string | null>(null);

  const loadAnalytics = React.useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await apiService.getAnalytics(selectedAssignment || undefined, classId || undefined);
      setAnalytics(data);
    } catch (err: any) {
      console.error('Error loading analytics:', err);
      setError(err.message || 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  }, [selectedAssignment, classId]);

  useEffect(() => {
    loadAnalytics();
  }, [loadAnalytics]);

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'No deadline';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  const getGradeColor = (grade: number | null) => {
    if (grade === null) return '#6B7280';
    if (grade >= 90) return '#10B981'; // green
    if (grade >= 80) return '#3B82F6'; // blue
    if (grade >= 70) return '#F59E0B'; // yellow
    if (grade >= 60) return '#F97316'; // orange
    return '#EF4444'; // red
  };

  const getSubmissionRateColor = (rate: number) => {
    if (rate >= 80) return '#10B981';
    if (rate >= 60) return '#3B82F6';
    if (rate >= 40) return '#F59E0B';
    return '#EF4444';
  };

  if (loading) {
    return (
      <div className="analytics-dashboard">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Loading analytics...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="analytics-dashboard">
        <div className="error-container">
          <p>Error: {error}</p>
          <button onClick={loadAnalytics}>Retry</button>
        </div>
      </div>
    );
  }

  if (!analytics || !analytics.assignments || analytics.assignments.length === 0) {
    return (
      <div className="analytics-dashboard">
        <div className="empty-state">
          <h2>No Analytics Available</h2>
          <p>Create assignments and wait for student submissions to see analytics.</p>
        </div>
      </div>
    );
  }

  const overall = analytics.overall_submission_rate !== undefined ? {
    submissionRate: analytics.overall_submission_rate,
    averageGrade: analytics.overall_average_grade,
    latePct: analytics.overall_late_pct || 0
  } : null;

  return (
    <div className="analytics-dashboard">
      <div className="analytics-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <h1>📊 Analytics Dashboard</h1>
          {classId && (
            <span style={{ 
              padding: '4px 12px', 
              background: 'var(--primary-light)', 
              borderRadius: '16px', 
              fontSize: '13px',
              color: 'var(--primary-color)',
              fontWeight: '500'
            }}>
              Class Analytics
            </span>
          )}
        </div>
        <div className="filter-controls" style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          {onClose && (
            <button
              onClick={onClose}
              style={{
                padding: '8px 16px',
                background: 'var(--bg-secondary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-color)',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: '500',
                fontSize: '0.875rem',
                transition: 'all 0.2s ease'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--bg-hover)';
                e.currentTarget.style.boxShadow = 'var(--shadow-sm)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'var(--bg-secondary)';
                e.currentTarget.style.boxShadow = 'none';
              }}
            >
              ← Back
            </button>
          )}
          <select 
            value={selectedAssignment || ''} 
            onChange={(e) => setSelectedAssignment(e.target.value || null)}
            className="assignment-filter"
          >
            <option value="">All Assignments</option>
            {analytics.assignments.map(assignment => (
              <option key={assignment.assignment_id} value={assignment.assignment_id}>
                {assignment.topic}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Overall Stats */}
      {overall && (
        <div className="overall-stats">
          <div className="stat-card">
            <div className="stat-icon">👥</div>
            <div className="stat-content">
              <div className="stat-value">{analytics.total_students}</div>
              <div className="stat-label">Total Students</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon">📝</div>
            <div className="stat-content">
              <div className="stat-value">{analytics.total_assignments}</div>
              <div className="stat-label">Total Assignments</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon">✅</div>
            <div className="stat-content">
              <div className="stat-value" style={{ color: getSubmissionRateColor(overall.submissionRate) }}>
                {overall.submissionRate.toFixed(1)}%
              </div>
              <div className="stat-label">Overall Submission Rate</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon">📊</div>
            <div className="stat-content">
              <div className="stat-value" style={{ color: getGradeColor(overall.averageGrade ?? null) }}>
                {overall.averageGrade !== null && overall.averageGrade !== undefined ? overall.averageGrade.toFixed(1) : 'N/A'}
              </div>
              <div className="stat-label">Average Grade</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon">⏰</div>
            <div className="stat-content">
              <div className="stat-value" style={{ color: overall.latePct > 20 ? '#EF4444' : '#10B981' }}>
                {overall.latePct.toFixed(1)}%
              </div>
              <div className="stat-label">Late Submissions</div>
            </div>
          </div>
        </div>
      )}

      {/* Assignment Analytics */}
      <div className="assignments-analytics">
        <h2>Assignment Details</h2>
        <div className="assignments-grid">
          {analytics.assignments.map(assignment => (
            <div key={assignment.assignment_id} className="assignment-card">
              <div className="assignment-header">
                <h3>{assignment.topic}</h3>
                <span className={`status-badge ${assignment.published ? 'published' : 'draft'}`}>
                  {assignment.published ? 'Published' : 'Draft'}
                </span>
              </div>
              
              <div className="quick-view">
                <div className="quick-stat submitted">
                  <span className="quick-label">Submitted</span>
                  <span className="quick-value">{assignment.students_submitted}</span>
                </div>
                <div className="quick-stat pending">
                  <span className="quick-label">Pending</span>
                  <span className="quick-value">{assignment.students_pending}</span>
                </div>
              </div>

              <div className="metrics">
                <div className="metric">
                  <div className="metric-label">Submission Rate</div>
                  <div className="metric-bar-container">
                    <div 
                      className="metric-bar"
                      style={{ 
                        width: `${assignment.submission_rate}%`,
                        backgroundColor: getSubmissionRateColor(assignment.submission_rate)
                      }}
                    ></div>
                    <span className="metric-value">{assignment.submission_rate}%</span>
                  </div>
                </div>

                <div className="metric">
                  <div className="metric-label">Average Grade</div>
                  <div className="metric-value-large" style={{ color: getGradeColor(assignment.average_grade) }}>
                    {assignment.average_grade !== null 
                      ? `${assignment.average_grade.toFixed(1)}%` 
                      : 'Not Graded'}
                  </div>
                  {assignment.graded_count > 0 && (
                    <div className="metric-subtext">
                      {assignment.graded_count} of {assignment.total_submissions} graded
                    </div>
                  )}
                </div>

                <div className="metric">
                  <div className="metric-label">Late Submissions</div>
                  <div className="metric-value-large" style={{ 
                    color: assignment.late_submissions_pct > 20 ? '#EF4444' : '#10B981' 
                  }}>
                    {assignment.late_submissions_pct}%
                  </div>
                </div>
              </div>

              <div className="assignment-footer">
                <div className="footer-item">
                  <span className="footer-label">Due Date:</span>
                  <span className="footer-value">{formatDate(assignment.due_date)}</span>
                </div>
                <div className="footer-item">
                  <span className="footer-label">Total Students:</span>
                  <span className="footer-value">{assignment.total_students}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default AnalyticsDashboard;

