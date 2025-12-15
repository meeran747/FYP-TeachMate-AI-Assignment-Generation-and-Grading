import React, { useState, useEffect } from 'react';
import { apiService, createDevToken } from '../services/api';
import { useToast } from '../hooks/useToast';
import Toast from './Toast';
import Settings from './Settings';
import './Dashboard.css';
import './CommonStyles.css';

interface AdminDashboardProps {
  user: any;
  profile: any;
  onSignOut: () => void;
}

const AdminDashboard: React.FC<AdminDashboardProps> = ({ user, profile, onSignOut }) => {
  const { toasts, showToast, removeToast } = useToast();
  const [showSettings, setShowSettings] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'users' | 'classes' | 'assignments'>('overview');
  const [stats, setStats] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [classes, setClasses] = useState<any[]>([]);
  const [assignments, setAssignments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [userFilter, setUserFilter] = useState<string>('all');
  const [showUserModal, setShowUserModal] = useState(false);
  const [selectedUser, setSelectedUser] = useState<any>(null);
  const [showClassModal, setShowClassModal] = useState(false);
  const [selectedClass, setSelectedClass] = useState<any>(null);
  const [showAssignTeacherModal, setShowAssignTeacherModal] = useState(false);
  const [showEnrollStudentModal, setShowEnrollStudentModal] = useState(false);
  const [teacherEmail, setTeacherEmail] = useState('');
  const [studentEmail, setStudentEmail] = useState('');

  useEffect(() => {
    if (user && profile) {
      const token = createDevToken(user.id, user.email, profile.role, profile.name);
      localStorage.setItem('auth_token', token);
    }
    loadData();
  }, [user, profile, activeTab, userFilter]);

  const loadData = async () => {
    setLoading(true);
    try {
      if (activeTab === 'overview') {
        const statsResult = await apiService.getAdminStats();
        if (statsResult.success) {
          setStats(statsResult.stats);
        }
      } else if (activeTab === 'users') {
        const role = userFilter !== 'all' ? userFilter : undefined;
        const usersResult = await apiService.getAllUsers(role);
        if (usersResult.success) {
          setUsers(usersResult.users || []);
        }
      } else if (activeTab === 'classes') {
        const classesResult = await apiService.getAllClasses();
        if (classesResult.success) {
          setClasses(classesResult.classes || []);
        }
      } else if (activeTab === 'assignments') {
        const assignmentsResult = await apiService.getAllAssignments();
        if (assignmentsResult.success) {
          setAssignments(assignmentsResult.assignments || []);
        }
      }
    } catch (error: any) {
      console.error('Error loading admin data:', error);
      showToast(error.message || 'Failed to load data', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateUserRole = async (userId: string, newRole: string) => {
    try {
      await apiService.updateUserRole(userId, newRole);
      showToast(`✓ User role updated to ${newRole}`, 'success');
      loadData();
    } catch (error: any) {
      showToast(error.message || 'Failed to update user role', 'error');
    }
  };

  const handleDeleteUser = async (userId: string) => {
    if (!window.confirm('Are you sure you want to delete this user? This action cannot be undone.')) {
      return;
    }
    try {
      await apiService.deleteUser(userId);
      showToast('✓ User deleted successfully', 'success');
      loadData();
    } catch (error: any) {
      showToast(error.message || 'Failed to delete user', 'error');
    }
  };

  const handleAssignTeacher = async () => {
    if (!selectedClass || !teacherEmail.trim()) {
      showToast('Please enter a teacher email', 'warning');
      return;
    }
    try {
      // Find teacher by email
      const teacherUsers = users.filter(u => u.email === teacherEmail.trim() && u.role === 'teacher');
      if (teacherUsers.length === 0) {
        showToast('Teacher not found with that email', 'error');
        return;
      }
      await apiService.assignTeacherToClass(selectedClass.id, teacherUsers[0].id);
      showToast('✓ Teacher assigned to class', 'success');
      setShowAssignTeacherModal(false);
      setTeacherEmail('');
      loadData();
    } catch (error: any) {
      showToast(error.message || 'Failed to assign teacher', 'error');
    }
  };

  const handleEnrollStudent = async () => {
    if (!selectedClass || !studentEmail.trim()) {
      showToast('Please enter a student email', 'warning');
      return;
    }
    try {
      // Find student by email
      const studentUsers = users.filter(u => u.email === studentEmail.trim() && u.role === 'student');
      if (studentUsers.length === 0) {
        showToast('Student not found with that email', 'error');
        return;
      }
      await apiService.enrollStudentInClass(selectedClass.id, studentUsers[0].id);
      showToast('✓ Student enrolled in class', 'success');
      setShowEnrollStudentModal(false);
      setStudentEmail('');
      loadData();
    } catch (error: any) {
      showToast(error.message || 'Failed to enroll student', 'error');
    }
  };

  const handleRemoveUserFromClass = async (classId: string, userId: string, userRole: string) => {
    if (!window.confirm(`Are you sure you want to remove this ${userRole} from the class?`)) {
      return;
    }
    try {
      await apiService.removeUserFromClass(classId, userId, userRole);
      showToast(`✓ ${userRole.charAt(0).toUpperCase() + userRole.slice(1)} removed from class`, 'success');
      loadData();
    } catch (error: any) {
      showToast(error.message || 'Failed to remove user from class', 'error');
    }
  };

  const handleDeleteClass = async (classId: string) => {
    if (!window.confirm('Are you sure you want to delete this class? This action cannot be undone.')) {
      return;
    }
    try {
      await apiService.deleteClass(classId);
      showToast('✓ Class deleted successfully', 'success');
      loadData();
    } catch (error: any) {
      showToast(error.message || 'Failed to delete class', 'error');
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
            <span>Admin: {profile.name}</span>
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
          <div className="section-header">
            <h2>Admin Dashboard</h2>
            <p>Manage users, classes, and system-wide settings</p>
          </div>

          {/* Tabs */}
          <div className="admin-tabs">
            <button
              className={`admin-tab ${activeTab === 'overview' ? 'active' : ''}`}
              onClick={() => setActiveTab('overview')}
            >
              📊 Overview
            </button>
            <button
              className={`admin-tab ${activeTab === 'users' ? 'active' : ''}`}
              onClick={() => setActiveTab('users')}
            >
              👥 Users
            </button>
            <button
              className={`admin-tab ${activeTab === 'classes' ? 'active' : ''}`}
              onClick={() => setActiveTab('classes')}
            >
              📚 Classes
            </button>
            <button
              className={`admin-tab ${activeTab === 'assignments' ? 'active' : ''}`}
              onClick={() => setActiveTab('assignments')}
            >
              📝 Assignments
            </button>
          </div>

          {loading ? (
            <div className="loading">
              <div className="spinner"></div>
              <p>Loading...</p>
            </div>
          ) : (
            <>
              {/* Overview Tab */}
              {activeTab === 'overview' && stats && (
                <div className="admin-overview">
                  <div className="stats-grid">
                    <div className="stat-card-admin">
                      <div className="stat-icon-admin">👥</div>
                      <div className="stat-content-admin">
                        <div className="stat-value-admin">{stats.total_users || 0}</div>
                        <div className="stat-label-admin">Total Users</div>
                      </div>
                    </div>
                    <div className="stat-card-admin">
                      <div className="stat-icon-admin">👨‍🏫</div>
                      <div className="stat-content-admin">
                        <div className="stat-value-admin">{stats.total_teachers || 0}</div>
                        <div className="stat-label-admin">Teachers</div>
                      </div>
                    </div>
                    <div className="stat-card-admin">
                      <div className="stat-icon-admin">🎓</div>
                      <div className="stat-content-admin">
                        <div className="stat-value-admin">{stats.total_students || 0}</div>
                        <div className="stat-label-admin">Students</div>
                      </div>
                    </div>
                    <div className="stat-card-admin">
                      <div className="stat-icon-admin">👑</div>
                      <div className="stat-content-admin">
                        <div className="stat-value-admin">{stats.total_admins || 0}</div>
                        <div className="stat-label-admin">Admins</div>
                      </div>
                    </div>
                    <div className="stat-card-admin">
                      <div className="stat-icon-admin">📚</div>
                      <div className="stat-content-admin">
                        <div className="stat-value-admin">{stats.total_classes || 0}</div>
                        <div className="stat-label-admin">Classes</div>
                      </div>
                    </div>
                    <div className="stat-card-admin">
                      <div className="stat-icon-admin">📝</div>
                      <div className="stat-content-admin">
                        <div className="stat-value-admin">{stats.total_assignments || 0}</div>
                        <div className="stat-label-admin">Assignments</div>
                      </div>
                    </div>
                    <div className="stat-card-admin">
                      <div className="stat-icon-admin">📥</div>
                      <div className="stat-content-admin">
                        <div className="stat-value-admin">{stats.total_submissions || 0}</div>
                        <div className="stat-label-admin">Submissions</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Users Tab */}
              {activeTab === 'users' && (
                <div className="admin-users">
                  <div className="admin-section-header">
                    <h3>User Management</h3>
                    <div className="filter-controls">
                      <select
                        value={userFilter}
                        onChange={(e) => setUserFilter(e.target.value)}
                        className="assignment-filter"
                      >
                        <option value="all">All Users</option>
                        <option value="admin">Admins</option>
                        <option value="teacher">Teachers</option>
                        <option value="student">Students</option>
                      </select>
                    </div>
                  </div>
                  <div className="users-table-container">
                    <table className="admin-table">
                      <thead>
                        <tr>
                          <th>Name</th>
                          <th>Email</th>
                          <th>Role</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {users.map((u) => (
                          <tr key={u.id}>
                            <td>{u.name || 'N/A'}</td>
                            <td>{u.email}</td>
                            <td>
                              <span className={`role-badge role-${u.role}`}>
                                {u.role}
                              </span>
                            </td>
                            <td>
                              <div className="action-buttons-group">
                                <select
                                  value={u.role}
                                  onChange={(e) => handleUpdateUserRole(u.id, e.target.value)}
                                  className="role-select"
                                  disabled={u.id === user.id}
                                >
                                  <option value="admin">Admin</option>
                                  <option value="teacher">Teacher</option>
                                  <option value="student">Student</option>
                                </select>
                                {u.id !== user.id && (
                                  <button
                                    onClick={() => handleDeleteUser(u.id)}
                                    className="btn-icon btn-delete"
                                  >
                                    🗑️ Delete
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {users.length === 0 && (
                      <div className="empty-state">
                        <p>No users found</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Classes Tab */}
              {activeTab === 'classes' && (
                <div className="admin-classes">
                  <div className="admin-section-header">
                    <h3>Class Management</h3>
                  </div>
                  <div className="classes-list">
                    {classes.map((cls) => (
                      <div key={cls.id} className="class-card-admin">
                        <div className="class-card-header-admin">
                          <div>
                            <h4>{cls.name}</h4>
                            {cls.code && <p className="class-code">Code: {cls.code}</p>}
                            {cls.description && <p className="class-description">{cls.description}</p>}
                          </div>
                          <button
                            onClick={() => handleDeleteClass(cls.id)}
                            className="btn-icon btn-delete"
                          >
                            🗑️ Delete
                          </button>
                        </div>
                        <div className="class-actions-admin">
                          <button
                            onClick={() => {
                              setSelectedClass(cls);
                              setShowAssignTeacherModal(true);
                            }}
                            className="btn-icon btn-edit"
                          >
                            ➕ Assign Teacher
                          </button>
                          <button
                            onClick={() => {
                              setSelectedClass(cls);
                              setShowEnrollStudentModal(true);
                            }}
                            className="btn-icon btn-edit"
                          >
                            ➕ Enroll Student
                          </button>
                        </div>
                      </div>
                    ))}
                    {classes.length === 0 && (
                      <div className="empty-state">
                        <p>No classes found</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Assignments Tab */}
              {activeTab === 'assignments' && (
                <div className="admin-assignments">
                  <div className="admin-section-header">
                    <h3>All Assignments</h3>
                  </div>
                  <div className="assignments-list">
                    {assignments.map((assignment) => (
                      <div key={assignment.id} className="assignment-card-container">
                        <div className="assignment-card-header">
                          <div className="assignment-title-section">
                            <h3 className="assignment-title">{assignment.topic}</h3>
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
                                    {new Date(assignment.deadline).toLocaleString()}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                    {assignments.length === 0 && (
                      <div className="empty-state">
                        <p>No assignments found</p>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </main>

      {/* Assign Teacher Modal */}
      {showAssignTeacherModal && selectedClass && (
        <div className="modal-overlay" onClick={() => setShowAssignTeacherModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Assign Teacher to {selectedClass.name}</h3>
              <button className="close-button" onClick={() => setShowAssignTeacherModal(false)}>×</button>
            </div>
            <div style={{ padding: '20px' }}>
              <div className="form-group">
                <label>Teacher Email</label>
                <input
                  type="email"
                  value={teacherEmail}
                  onChange={(e) => setTeacherEmail(e.target.value)}
                  placeholder="Enter teacher email"
                />
              </div>
              <div className="form-actions">
                <button className="cancel-button" onClick={() => setShowAssignTeacherModal(false)}>Cancel</button>
                <button className="submit-button" onClick={handleAssignTeacher}>Assign</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Enroll Student Modal */}
      {showEnrollStudentModal && selectedClass && (
        <div className="modal-overlay" onClick={() => setShowEnrollStudentModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Enroll Student in {selectedClass.name}</h3>
              <button className="close-button" onClick={() => setShowEnrollStudentModal(false)}>×</button>
            </div>
            <div style={{ padding: '20px' }}>
              <div className="form-group">
                <label>Student Email</label>
                <input
                  type="email"
                  value={studentEmail}
                  onChange={(e) => setStudentEmail(e.target.value)}
                  placeholder="Enter student email"
                />
              </div>
              <div className="form-actions">
                <button className="cancel-button" onClick={() => setShowEnrollStudentModal(false)}>Cancel</button>
                <button className="submit-button" onClick={handleEnrollStudent}>Enroll</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showSettings && <Settings onClose={() => setShowSettings(false)} />}
    </div>
  );
};

export default AdminDashboard;

