import React, { useState } from 'react';
import { authService, SignupData } from '../services/supabase';
import './SignupPortal.css';

// SignupData interface is now imported from supabase service

interface SignupPortalProps {
  onSubmit?: (data: SignupData) => void;
  onSignupSuccess?: () => void;
}

const SignupPortal: React.FC<SignupPortalProps> = ({ onSubmit, onSignupSuccess }) => {
  const [step, setStep] = useState<'userType' | 'details'>('userType');
  const [userType, setUserType] = useState<'student' | 'teacher' | null>(null);
  const [formData, setFormData] = useState<SignupData & { roll_number?: string }>({
    firstName: '',
    lastName: '',
    email: '',
    password: '',
    confirmPassword: '',
    userType: 'student',
    roll_number: ''
  });
  const [errors, setErrors] = useState<Partial<SignupData>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');

  const handleUserTypeSelect = (type: 'student' | 'teacher') => {
    setUserType(type);
    setFormData(prev => ({ ...prev, userType: type }));
    setStep('details');
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    
    // Clear error when user starts typing
    if (errors[name as keyof SignupData]) {
      setErrors(prev => ({ ...prev, [name]: '' }));
    }
  };

  const validateForm = (): boolean => {
    const newErrors: Partial<SignupData> = {};

    if (!formData.firstName.trim()) {
      newErrors.firstName = 'First name is required';
    }

    if (!formData.lastName.trim()) {
      newErrors.lastName = 'Last name is required';
    }

    if (!formData.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      newErrors.email = 'Email is invalid';
    }

    if (!formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters';
    }

    if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    // Validate roll number for students
    if (userType === 'student' && !(formData as any).roll_number?.trim()) {
      (newErrors as any).roll_number = 'Roll number is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (validateForm()) {
      setIsLoading(true);
      setSuccessMessage('');
      
      try {
        if (onSubmit) {
          onSubmit(formData);
        } else {
          // Use Supabase authentication
          const result = await authService.signUp(formData);
          
          if (result.success) {
            setSuccessMessage('Account created successfully! You can now sign in.');
            // Reset form
            setFormData({
              firstName: '',
              lastName: '',
              email: '',
              password: '',
              confirmPassword: '',
              userType: 'student',
              roll_number: ''
            });
            setStep('userType');
            setUserType(null);
            
            // Call success callback after a short delay
            setTimeout(() => {
              if (onSignupSuccess) {
                onSignupSuccess();
              }
            }, 2000);
          } else {
            setErrors({ email: result.error || 'An error occurred during signup' });
          }
        }
      } catch (error) {
        console.error('Signup error:', error);
        setErrors({ email: 'An unexpected error occurred. Please try again.' });
      } finally {
        setIsLoading(false);
      }
    }
  };

  const goBack = () => {
    setStep('userType');
    setUserType(null);
  };

  return (
    <div className="signup-portal">
      <div className="signup-container">
        <div className="signup-header">
          <h1>TeachMate</h1>
          <p>Join the future of education</p>
        </div>

        {step === 'userType' && (
          <div className="user-type-selection">
            <h2>Choose your role</h2>
            <div className="user-type-cards">
              <div 
                className="user-type-card"
                onClick={() => handleUserTypeSelect('student')}
              >
                <div className="card-icon">🎓</div>
                <h3>Student</h3>
                <p>Join classes, submit assignments, and collaborate with peers</p>
              </div>
              
              <div 
                className="user-type-card"
                onClick={() => handleUserTypeSelect('teacher')}
              >
                <div className="card-icon">👨‍🏫</div>
                <h3>Teacher</h3>
                <p>Create classes, manage assignments, and track student progress</p>
              </div>
            </div>
          </div>
        )}

        {step === 'details' && (
          <form className="signup-form" onSubmit={handleSubmit}>
            <div className="form-header">
              <button type="button" className="back-button" onClick={goBack}>
                ← Back
              </button>
              <h2>Create your {userType} account</h2>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="firstName">First Name</label>
                <input
                  type="text"
                  id="firstName"
                  name="firstName"
                  value={formData.firstName}
                  onChange={handleInputChange}
                  className={errors.firstName ? 'error' : ''}
                  placeholder="Enter your first name"
                />
                {errors.firstName && <span className="error-message">{errors.firstName}</span>}
              </div>

              <div className="form-group">
                <label htmlFor="lastName">Last Name</label>
                <input
                  type="text"
                  id="lastName"
                  name="lastName"
                  value={formData.lastName}
                  onChange={handleInputChange}
                  className={errors.lastName ? 'error' : ''}
                  placeholder="Enter your last name"
                />
                {errors.lastName && <span className="error-message">{errors.lastName}</span>}
              </div>
            </div>

            {userType === 'student' && (
              <div className="form-group">
                <label htmlFor="roll_number">Roll Number *</label>
                <input
                  type="text"
                  id="roll_number"
                  name="roll_number"
                  value={(formData as any).roll_number || ''}
                  onChange={(e) => setFormData(prev => ({ ...prev, roll_number: e.target.value }))}
                  placeholder="e.g., 2021-CS-123"
                  required
                  className={(errors as any).roll_number ? 'error' : ''}
                />
                {(errors as any).roll_number && <span className="error-message">{(errors as any).roll_number}</span>}
                <small style={{ color: '#666', fontSize: '0.85rem', display: 'block', marginTop: '5px' }}>
                  Your roll number will be used for assignment submissions
                </small>
              </div>
            )}

            <div className="form-group">
              <label htmlFor="email">Email Address</label>
              <input
                type="email"
                id="email"
                name="email"
                value={formData.email}
                onChange={handleInputChange}
                className={errors.email ? 'error' : ''}
                placeholder="Enter your email address"
              />
              {errors.email && <span className="error-message">{errors.email}</span>}
            </div>


            <div className="form-row">
              <div className="form-group">
                <label htmlFor="password">Password</label>
                <input
                  type="password"
                  id="password"
                  name="password"
                  value={formData.password}
                  onChange={handleInputChange}
                  className={errors.password ? 'error' : ''}
                  placeholder="Create a password"
                />
                {errors.password && <span className="error-message">{errors.password}</span>}
              </div>

              <div className="form-group">
                <label htmlFor="confirmPassword">Confirm Password</label>
                <input
                  type="password"
                  id="confirmPassword"
                  name="confirmPassword"
                  value={formData.confirmPassword}
                  onChange={handleInputChange}
                  className={errors.confirmPassword ? 'error' : ''}
                  placeholder="Confirm your password"
                />
                {errors.confirmPassword && <span className="error-message">{errors.confirmPassword}</span>}
              </div>
            </div>

            {successMessage && (
              <div className="success-message">
                {successMessage}
              </div>
            )}

            <button 
              type="submit" 
              className="submit-button"
              disabled={isLoading}
            >
              {isLoading ? 'Creating Account...' : 'Create Account'}
            </button>

            <div className="login-link">
              Already have an account? <a href="#login">Sign in</a>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default SignupPortal;
