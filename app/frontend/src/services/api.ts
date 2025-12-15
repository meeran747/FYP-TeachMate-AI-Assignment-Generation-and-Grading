/**
 * API Service for TeachMate Backend
 * Handles all API calls with proper authentication and RBAC support
 */

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Get auth token from localStorage
const getAuthToken = async (): Promise<string | null> => {
  // Get token from localStorage (stored during login)
  const token = localStorage.getItem('auth_token');
  if (token) {
    // Check if it's a real Supabase JWT (format: xxxx.yyyy.zzzz - 3 parts separated by dots)
    const parts = token.split('.');
    if (parts.length === 3) {
      // This is a real JWT token
      return token;
    } else {
      // Could be a dev token (base64 encoded JSON) - check if it's valid base64
      try {
        // Try to decode it to verify it's a valid dev token
        const decoded = atob(token);
        const tokenData = JSON.parse(decoded);
        if (tokenData && (tokenData.id || tokenData.role)) {
          // Valid dev token format - return it
          console.log('✓ Using dev token format');
          return token;
        }
      } catch (e) {
        // Not a valid dev token either - might be corrupted
        console.warn('⚠ Invalid token format detected, clearing localStorage');
      localStorage.removeItem('auth_token');
      localStorage.removeItem('user');
      return null;
      }
    }
  }
  
  // Fallback: Try to get from Supabase session (if using Supabase Auth)
  try {
    const { supabase } = await import('./supabase');
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.access_token) {
      return session.access_token;
    }
  } catch (e) {
    console.warn('Could not get Supabase session:', e);
  }
  
  return null;
};

// Create a simple token for development (base64 encoded JSON user info)
export const createDevToken = (userId: string, email: string, role: string, name?: string): string => {
  const tokenData = {
    id: userId,
    email: email,
    role: role,
    name: name || ''
  };
  return btoa(JSON.stringify(tokenData));
};

/**
 * Make authenticated API request
 */
const apiRequest = async (
  endpoint: string,
  options: RequestInit = {}
): Promise<Response> => {
  const token = await getAuthToken();
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
    console.log(`🔐 Sending request to ${endpoint} with token (length: ${token.length}, preview: ${token.substring(0, 30)}...)`);
  } else {
    console.warn(`⚠ No token available for request to ${endpoint}`);
  }
  
  const url = `${API_BASE_URL}${endpoint}`;
  
  const response = await fetch(url, {
    ...options,
    headers,
  });
  
  if (response.status === 401) {
    // Unauthorized - clear token and redirect to login
    console.error('401 Unauthorized - clearing token and redirecting to login');
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    window.location.href = '/';
  }
  
  return response;
};

export const apiService = {
  /**
   * Create assignment (Teacher/Admin only)
   */
  async createAssignment(data: {
    topic: string;
    description: string;
    type: string;
    num_questions: number;
    section?: string;
    deadline?: string;
    published?: boolean;
    class_id?: string;
  }) {
    const response = await apiRequest('/create-assignment', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to create assignment');
    }
    
    return response.json();
  },

  /**
   * Submit assignment (Student only)
   */
  async submitAssignment(data: {
    assignment_id: string;
    roll_number?: string;
    section?: string;
    answer_text?: string;
    file_url?: string;
  }) {
    const response = await apiRequest('/submit-assignment', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to submit assignment');
    }
    
    return response.json();
  },

  /**
   * Update assignment (Teacher only)
   */
  async updateAssignment(assignmentId: string, data: {
    topic: string;
    description: string;
    type: string;
    num_questions: number;
    section?: string;
    deadline?: string;
    published?: boolean;
  }) {
    const response = await apiRequest(`/update-assignment?assignment_id=${assignmentId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to update assignment');
    }
    
    return response.json();
  },

  /**
   * Delete assignment (Teacher only)
   */
  async deleteAssignment(assignmentId: string) {
    const response = await apiRequest(`/delete-assignment?assignment_id=${assignmentId}`, {
      method: 'DELETE',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to delete assignment');
    }
    
    return response.json();
  },

  /**
   * Get my classes (filtered by role)
   */
  async getMyClasses() {
    const response = await apiRequest('/get-my-classes', {
      method: 'GET',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to fetch classes');
    }
    
    return response.json();
  },

  /**
   * Create a new class (Teacher only)
   */
  async createClass(data: {
    name: string;
    code?: string;
    description?: string;
  }) {
    const response = await apiRequest('/create-class', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to create class');
    }
    
    return response.json();
  },

  /**
   * Enroll a student in a class (Teacher only)
   */
  async enrollStudent(studentId: string, classId: string) {
    const response = await apiRequest(`/enroll-student?student_id=${studentId}&class_id=${classId}`, {
      method: 'POST',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to enroll student');
    }
    
    return response.json();
  },

  /**
   * Get students in a class (Teacher only)
   */
  async getClassStudents(classId: string) {
    const response = await apiRequest(`/get-class-students?class_id=${classId}`, {
      method: 'GET',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to fetch class students');
    }
    
    return response.json();
  },

  /**
   * Enroll in a class using class code (Student only)
   */
  async enrollByCode(classCode: string) {
    const response = await apiRequest(`/enroll-by-code?class_code=${encodeURIComponent(classCode)}`, {
      method: 'POST',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to enroll in class');
    }
    
    return response.json();
  },

  /**
   * Get my assignments (filtered by role)
   */
  async getMyAssignments(classId?: string) {
    const endpoint = classId 
      ? `/get-my-assignments?class_id=${encodeURIComponent(classId)}`
      : '/get-my-assignments';
    
    const response = await apiRequest(endpoint);
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to fetch assignments');
    }
    
    return response.json();
  },

  /**
   * Get submissions (Teacher/Admin only)
   */
  async getSubmissions(assignmentId?: string) {
    const endpoint = assignmentId 
      ? `/get-submissions?assignment_id=${assignmentId}`
      : '/get-submissions';
    
    const response = await apiRequest(endpoint);
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to fetch submissions');
    }
    
    return response.json();
  },

  /**
   * Grade assignment (Teacher/Admin only)
   * Grades all submissions for an assignment using AI
   */
  async gradeAssignment(assignmentId: string) {
    const response = await apiRequest(`/grade-assignment?assignment_id=${assignmentId}`, {
      method: 'POST',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to grade assignment');
    }
    
    return response.json();
  },

  /**
   * Unsubmit assignment (Student only)
   * Deletes a submission for an assignment
   */
  async unsubmitAssignment(assignmentId: string) {
    const response = await apiRequest(`/unsubmit-assignment?assignment_id=${assignmentId}`, {
      method: 'DELETE',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to unsubmit assignment');
    }
    
    return response.json();
  },

  /**
   * Export grades as CSV (Teacher/Admin only)
   * Downloads a CSV file with all grades for an assignment
   */
  async exportGradesCSV(assignmentId: string) {
    const token = getAuthToken();
    const response = await fetch(`${API_BASE_URL}/export-grades-csv?assignment_id=${assignmentId}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to export grades');
    }
    
    // Get filename from Content-Disposition header or use default
    const contentDisposition = response.headers.get('Content-Disposition');
    let filename = 'grades.csv';
    if (contentDisposition) {
      const filenameMatch = contentDisposition.match(/filename="?(.+)"?/);
      if (filenameMatch) {
        filename = filenameMatch[1];
      }
    }
    
    // Download the file
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    
    return { success: true, filename };
  },

  /**
   * Health check
   */
  async healthCheck() {
    const response = await apiRequest('/health');
    return response.json();
  },

  /**
   * Register new user (Public endpoint - no auth required)
   */
  async register(data: {
    firstName: string;
    lastName: string;
    email: string;
    password: string;
    userType: 'student' | 'teacher';
    section?: string;
    teacherEmail?: string;
    roll_number?: string;
  }) {
    const response = await fetch(`${API_BASE_URL}/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Registration failed');
    }
    
    return response.json();
  },

  /**
   * Login user (Public endpoint - no auth required)
   * Returns: { success: boolean, user: {...}, token: string, message: string }
   */
  async login(email: string, password: string) {
    const response = await fetch(`${API_BASE_URL}/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password }),
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Login failed');
    }
    
    const data = await response.json();
    console.log('Login response:', { 
      success: data.success, 
      hasUser: !!data.user, 
      hasToken: !!data.token,
      tokenLength: data.token?.length,
      tokenPreview: data.token?.substring(0, 30) + '...'
    });
    
    return data;
  },

  /**
   * Get analytics for teacher's assignments
   */
  async getAnalytics(assignmentId?: string, classId?: string) {
    const params = new URLSearchParams();
    if (assignmentId) params.append('assignment_id', assignmentId);
    if (classId) params.append('class_id', classId);
    
    const endpoint = params.toString() 
      ? `/analytics?${params.toString()}`
      : `/analytics`;
    
    const response = await apiRequest(endpoint, {
      method: 'GET',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to fetch analytics');
    }
    
    return response.json();
  },

  // ============================================================
  // ADMIN API METHODS
  // ============================================================

  /**
   * Get system statistics (Admin only)
   */
  async getAdminStats() {
    const response = await apiRequest('/admin/stats', {
      method: 'GET',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to fetch admin stats');
    }
    
    return response.json();
  },

  /**
   * Get all users (Admin only)
   */
  async getAllUsers(role?: string) {
    const params = role ? `?role=${role}` : '';
    const response = await apiRequest(`/admin/users${params}`, {
      method: 'GET',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to fetch users');
    }
    
    return response.json();
  },

  /**
   * Get all classes (Admin only)
   */
  async getAllClasses() {
    const response = await apiRequest('/admin/classes', {
      method: 'GET',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to fetch classes');
    }
    
    return response.json();
  },

  /**
   * Get all assignments (Admin only)
   */
  async getAllAssignments() {
    const response = await apiRequest('/admin/assignments', {
      method: 'GET',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to fetch assignments');
    }
    
    return response.json();
  },

  /**
   * Update user role (Admin only)
   */
  async updateUserRole(userId: string, newRole: string) {
    const response = await apiRequest(`/admin/users/${userId}/role?new_role=${encodeURIComponent(newRole)}`, {
      method: 'PUT',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to update user role');
    }
    
    return response.json();
  },

  /**
   * Assign teacher to class (Admin only)
   */
  async assignTeacherToClass(classId: string, teacherId: string) {
    const response = await apiRequest(`/admin/classes/${classId}/teachers/${teacherId}`, {
      method: 'POST',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to assign teacher to class');
    }
    
    return response.json();
  },

  /**
   * Enroll student in class (Admin only)
   */
  async enrollStudentInClass(classId: string, studentId: string) {
    const response = await apiRequest(`/admin/classes/${classId}/students/${studentId}`, {
      method: 'POST',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to enroll student in class');
    }
    
    return response.json();
  },

  /**
   * Remove user from class (Admin only)
   */
  async removeUserFromClass(classId: string, userId: string, userRole: string) {
    const response = await apiRequest(`/admin/classes/${classId}/users/${userId}?user_role=${userRole}`, {
      method: 'DELETE',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to remove user from class');
    }
    
    return response.json();
  },

  /**
   * Delete user (Admin only)
   */
  async deleteUser(userId: string) {
    const response = await apiRequest(`/admin/users/${userId}`, {
      method: 'DELETE',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to delete user');
    }
    
    return response.json();
  },

  /**
   * Update class (Admin only)
   */
  async updateClass(classId: string, data: { name?: string; code?: string; description?: string }) {
    const response = await apiRequest(`/admin/classes/${classId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to update class');
    }
    
    return response.json();
  },

  /**
   * Delete class (Admin only)
   */
  async deleteClass(classId: string) {
    const response = await apiRequest(`/admin/classes/${classId}`, {
      method: 'DELETE',
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.detail || error.error || 'Failed to delete class');
    }
    
    return response.json();
  },
};

