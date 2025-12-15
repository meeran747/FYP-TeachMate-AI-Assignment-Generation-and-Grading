# TeachMate Frontend

A modern React-based signup portal for TeachMate, a classroom management platform similar to Google Classroom.

## Features

- **Dual User Types**: Separate signup flows for students and teachers
- **Modern UI**: Clean, responsive design with smooth animations
- **Form Validation**: Client-side validation with error handling
- **TypeScript**: Full type safety and better development experience
- **Supabase Integration**: Real-time authentication and database
- **Email Verification**: Built-in email verification flow

## Getting Started

### Prerequisites

- Node.js (version 14 or higher)
- npm or yarn
- Supabase account and project

### Installation

1. Navigate to the frontend directory:
   ```bash
   cd app/frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Set up environment variables:
   ```bash
   cp .env.example .env.local
   ```
   Then edit `.env.local` with your Supabase credentials:
   ```
   REACT_APP_SUPABASE_URL=your_supabase_url
   REACT_APP_SUPABASE_ANON_KEY=your_supabase_anon_key
   ```

4. Set up the database schema in Supabase:
   - Go to your Supabase project dashboard
   - Navigate to SQL Editor
   - Run the SQL commands from `supabase-schema.sql`

5. Start the development server:
   ```bash
   npm start
   ```

6. Open [http://localhost:3000](http://localhost:3000) to view it in the browser.

## Project Structure

```
app/frontend/
├── public/
│   └── index.html
├── src/
│   ├── components/
│   │   ├── SignupPortal.tsx
│   │   └── SignupPortal.css
│   ├── services/
│   │   └── supabase.ts
│   ├── App.tsx
│   ├── App.css
│   ├── index.tsx
│   └── index.css
├── supabase-schema.sql
├── package.json
└── tsconfig.json
```

## Components

### SignupPortal

The main signup component that handles:
- User type selection (Student/Teacher)
- Form validation
- Data collection for both user types
- Responsive design

#### Props

```typescript
interface SignupPortalProps {
  onSubmit?: (data: SignupData) => void;
}
```

#### SignupData Interface

```typescript
interface SignupData {
  firstName: string;
  lastName: string;
  email: string;
  password: string;
  confirmPassword: string;
  userType: 'student' | 'teacher';
  institution?: string;
  subject?: string; // Required for teachers
}
```

## Supabase Integration

The app is fully integrated with Supabase for authentication and database management:

### Authentication Service

The `authService` provides methods for:
- `signUp(data)` - Create new user accounts
- `signIn(email, password)` - Sign in existing users
- `signOut()` - Sign out current user
- `getCurrentUser()` - Get current authenticated user

### Database Schema

The app uses the following main tables:
- `user_profiles` - User information and preferences
- `classes` - Classroom management
- `class_enrollments` - Student-class relationships
- `assignments` - Assignment management
- `assignment_submissions` - Student submissions

### Row Level Security (RLS)

All tables have RLS enabled with appropriate policies:
- Users can only access their own data
- Teachers can manage their classes and assignments
- Students can view enrolled classes and submit assignments

### Custom Integration

You can still pass a custom `onSubmit` prop to override the default Supabase behavior:

```typescript
const handleCustomSignup = async (data: SignupData) => {
  // Custom signup logic
  console.log('Custom signup:', data);
};

<SignupPortal onSubmit={handleCustomSignup} />
```

## Available Scripts

- `npm start` - Runs the app in development mode
- `npm build` - Builds the app for production
- `npm test` - Launches the test runner
- `npm eject` - Ejects from Create React App (one-way operation)

## Styling

The app uses CSS modules with:
- Modern gradient backgrounds
- Smooth animations and transitions
- Responsive grid layouts
- Professional color scheme
- Mobile-first design approach
