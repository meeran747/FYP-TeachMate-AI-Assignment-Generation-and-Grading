import React, { useState, useEffect } from 'react';
import SignupPortal from './components/SignupPortal';
import SignIn from './components/SignIn';
import StudentDashboard from './components/StudentDashboard';
import TeacherDashboard from './components/TeacherDashboard';
import AdminDashboard from './components/AdminDashboard';
import { authService } from './services/supabase';
import { ThemeProvider } from './contexts/ThemeContext';
import './App.css';
import './components/CommonStyles.css';

type AppState = 'signup' | 'signin' | 'dashboard';

function App() {
  const [currentView, setCurrentView] = useState<AppState>('signin');
  const [user, setUser] = useState<any>(null);
  const [profile, setProfile] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(false); // No need to check auth state in simple version
  }, []);


  const handleSignInSuccess = (userData: any) => {
    setUser(userData);
    setProfile(userData); // In simple auth, user data is the profile
    setCurrentView('dashboard');
  };

  const handleSignOut = async () => {
    await authService.signOut();
    setUser(null);
    setProfile(null);
    setCurrentView('signin');
  };

  const handleSignupSuccess = () => {
    setCurrentView('signin');
  };

  if (isLoading) {
    return (
      <div className="App">
        <div className="loading-screen">
          <div className="spinner"></div>
          <p>Loading TeachMate...</p>
        </div>
      </div>
    );
  }

  return (
    <ThemeProvider>
      <div className="App">
        {currentView === 'signup' && (
          <SignupPortal onSignupSuccess={handleSignupSuccess} />
        )}
        
        {currentView === 'signin' && (
          <SignIn 
            onSignInSuccess={handleSignInSuccess} 
            onSwitchToSignup={() => setCurrentView('signup')}
          />
        )}
        
        {currentView === 'dashboard' && user && profile && (
          <>
            {profile.role === 'admin' ? (
              <AdminDashboard 
                user={user} 
                profile={profile} 
                onSignOut={handleSignOut} 
              />
            ) : profile.role === 'student' ? (
              <StudentDashboard 
                user={user} 
                profile={profile} 
                onSignOut={handleSignOut} 
              />
            ) : (
              <TeacherDashboard 
                user={user} 
                profile={profile} 
                onSignOut={handleSignOut} 
              />
            )}
          </>
        )}
      </div>
    </ThemeProvider>
  );
}

export default App;
