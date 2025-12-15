import { createClient } from '@supabase/supabase-js';

// Get Supabase credentials from environment variables (from .env.local) or use defaults
const supabaseUrl = process.env.REACT_APP_SUPABASE_URL || 'https://njpytzdrqtfoqcqwodao.supabase.co';
const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5qcHl0emRycXRmb3FjcXdvZGFvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDA4MTk5NzYsImV4cCI6MjA1NjM5NTk3Nn0.i5UjYYoBPY4LFkidVQV2BYtD41-UiXWWNVfECR8M5Q0';

// Log which Supabase project is being used (for debugging)
if (process.env.REACT_APP_SUPABASE_URL) {
  console.log('✓ Using Supabase URL from .env.local:', process.env.REACT_APP_SUPABASE_URL);
} else {
  console.warn('⚠ Using default Supabase URL. Create .env.local with REACT_APP_SUPABASE_URL to use your own project.');
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  role: 'student' | 'teacher';
}

export interface SignupData {
  firstName: string;
  lastName: string;
  email: string;
  password: string;
  confirmPassword: string;
  userType: 'student' | 'teacher';
  section?: string;  // For teachers
  teacherEmail?: string;  // For students
}

export const authService = {
  async signUp(data: SignupData) {
    try {
      console.log('Registering user via backend API:', data.email);
      
      // Call backend API for registration (uses service role, bypasses RLS)
      const apiService = (await import('./api')).apiService;
      const result = await apiService.register({
        firstName: data.firstName,
        lastName: data.lastName,
        email: data.email,
        password: data.password,
        userType: data.userType,
        section: data.section,
        teacherEmail: data.teacherEmail,
        roll_number: (data as any).roll_number,
      });

      if (result.success && result.user) {
        console.log('User registered successfully:', result.user);
        
        // Store user in localStorage for session management
        localStorage.setItem('user', JSON.stringify(result.user));
        
        return { success: true, user: result.user };
      } else {
        return { success: false, error: result.error || result.message || 'Registration failed' };
      }
    } catch (error: any) {
      console.error('Registration error:', error);
      return { success: false, error: error.message || 'Registration failed' };
    }
  },

  async signIn(email: string, password: string) {
    try {
      console.log('Signing in user via backend API:', email);
      
      // Call backend API for login
      const apiService = (await import('./api')).apiService;
      const result = await apiService.login(email, password);

      if (result.success && result.user && result.token) {
        console.log('User signed in successfully:', result.user);
        console.log('Token received (first 50 chars):', result.token.substring(0, 50));
        console.log('Token length:', result.token.length);
        
        // Clear any old tokens first
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user');
        
        // Store user and REAL Supabase JWT token in localStorage
        localStorage.setItem('user', JSON.stringify(result.user));
        localStorage.setItem('auth_token', result.token); // This is the real Supabase JWT
        
        console.log('✓ Token stored in localStorage');
        
        return { success: true, user: result.user };
      } else {
        console.error('Login failed:', result);
        return { success: false, error: result.error || result.message || 'Invalid email or password' };
      }
    } catch (error: any) {
      console.error('Signin error:', error);
      return { success: false, error: error.message || 'Invalid email or password' };
    }
  },

  async signOut() {
    // Clear localStorage
    localStorage.removeItem('user');
    localStorage.removeItem('auth_token');
    return { success: true };
  }
};
