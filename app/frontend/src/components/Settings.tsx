import React, { useState } from 'react';
import { useTheme } from '../contexts/ThemeContext';
import './Settings.css';

interface SettingsProps {
  onClose: () => void;
}

const Settings: React.FC<SettingsProps> = ({ onClose }) => {
  const { theme, setTheme } = useTheme();
  const [isOpen, setIsOpen] = useState(true);

  const handleClose = () => {
    setIsOpen(false);
    setTimeout(onClose, 200);
  };

  const handleThemeChange = (newTheme: 'light' | 'dark' | 'system') => {
    setTheme(newTheme);
  };

  if (!isOpen) return null;

  return (
    <div className="settings-overlay" onClick={handleClose}>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h2>Settings</h2>
          <button className="settings-close" onClick={handleClose}>×</button>
        </div>
        
        <div className="settings-content">
          <div className="settings-section">
            <h3>Appearance</h3>
            <div className="theme-options">
              <label className={`theme-option ${theme === 'light' ? 'active' : ''}`}>
                <input
                  type="radio"
                  name="theme"
                  value="light"
                  checked={theme === 'light'}
                  onChange={() => handleThemeChange('light')}
                />
                <div className="theme-option-content">
                  <div className="theme-icon">☀️</div>
                  <div>
                    <div className="theme-name">Light</div>
                    <div className="theme-desc">Light theme</div>
                  </div>
                </div>
              </label>
              
              <label className={`theme-option ${theme === 'dark' ? 'active' : ''}`}>
                <input
                  type="radio"
                  name="theme"
                  value="dark"
                  checked={theme === 'dark'}
                  onChange={() => handleThemeChange('dark')}
                />
                <div className="theme-option-content">
                  <div className="theme-icon">🌙</div>
                  <div>
                    <div className="theme-name">Dark</div>
                    <div className="theme-desc">Dark theme</div>
                  </div>
                </div>
              </label>
              
              <label className={`theme-option ${theme === 'system' ? 'active' : ''}`}>
                <input
                  type="radio"
                  name="theme"
                  value="system"
                  checked={theme === 'system'}
                  onChange={() => handleThemeChange('system')}
                />
                <div className="theme-option-content">
                  <div className="theme-icon">💻</div>
                  <div>
                    <div className="theme-name">System</div>
                    <div className="theme-desc">Use system default</div>
                  </div>
                </div>
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;

