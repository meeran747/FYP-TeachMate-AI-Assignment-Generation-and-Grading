# RBAC and Multi-Tenant Setup Guide

This guide explains how to set up the Role-Based Access Control (RBAC) and multi-tenant isolation system for TeachMate.

## 📋 Overview

The RBAC system provides:
- **3 Roles**: Admin, Teacher, Student
- **Multi-tenant isolation**: Zero data leakage between tenants
- **RLS (Row-Level Security)**: Database-level access control
- **Audit logging**: Research-grade tracking of all actions
- **Teacher-student relationships**: Students belong to one teacher

## 🗄️ Database Setup

### Step 1: Run the RBAC Schema

1. Go to your Supabase project dashboard
2. Navigate to **SQL Editor**
3. Run the SQL from `rbac_schema.sql`:

```sql
-- Copy and paste the entire contents of rbac_schema.sql
```

This will create:
- `profiles` table with roles and relationships
- `assignments` table with tenant isolation
- `submissions` table
- `audit_logs` table for tracking
- All RLS policies

### Step 2: Verify Tables

Check that all tables were created:
```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('profiles', 'assignments', 'submissions', 'audit_logs');
```

### Step 3: Create Test Users

```sql
-- Create an admin
INSERT INTO profiles (email, name, role) 
VALUES ('admin@teachmate.com', 'Admin User', 'admin');

-- Create a teacher
INSERT INTO profiles (email, name, role, section) 
VALUES ('teacher@teachmate.com', 'Teacher User', 'teacher', 'CS-101-A');

-- Create a student (assigned to teacher)
INSERT INTO profiles (email, name, role, teacher_id) 
VALUES ('student@teachmate.com', 'Student User', 'student', 
        (SELECT id FROM profiles WHERE email = 'teacher@teachmate.com'));
```

## 🔐 Environment Variables

Add these to your `.env` file in `app/backend/`:

```bash
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key  # Service role key (not anon key!)

# LLM Configuration
LLM_PROVIDER=groq  # or 'openai'
GROQ_API_KEY=your-groq-key  # if using Groq
OPENAI_API_KEY=your-openai-key  # if using OpenAI

# Embedding Configuration
EMBEDDING_PROVIDER=huggingface  # Free, local embeddings
```

**Important**: Use the **Service Role Key** (not the anon key) for backend operations. This allows the backend to bypass RLS when needed.

## 🚀 Running the RBAC Backend

### Option 1: Use the New RBAC Backend (Recommended)

```bash
cd app/backend
source venv/bin/activate
python main_rbac.py
```

### Option 2: Update Existing Backend

You can also update `main.py` to use the RBAC system by importing from `main_rbac.py`.

## 📡 API Endpoints

### Teacher Endpoints

#### Create Assignment
```bash
POST /create-assignment
Authorization: Bearer <token>

{
  "topic": "Data Science",
  "description": "ML algorithms assignment",
  "type": "theoretical",
  "num_questions": 5,
  "section": "CS-101-A"
}
```

**Access**: Teachers and Admins only

#### Get My Assignments
```bash
GET /get-my-assignments
Authorization: Bearer <token>
```

**Access**: All authenticated users (filtered by role)

#### Get Submissions
```bash
GET /get-submissions?assignment_id=<optional>
Authorization: Bearer <token>
```

**Access**: Teachers and Admins only (only their students' submissions)

### Student Endpoints

#### Submit Assignment
```bash
POST /submit-assignment
Authorization: Bearer <token>

{
  "assignment_id": "uuid",
  "roll_number": "2024-CS-001",
  "section": "CS-101-A",
  "answer_text": "My answer...",
  "file_url": "https://storage.supabase.co/..."
}
```

**Access**: Students only

### Admin Endpoints

#### Admin Stats
```bash
GET /admin/stats
Authorization: Bearer <token>
```

**Access**: Admins only

## 🔍 Data Visibility

### Students See:
- ✅ Assignments from their teacher only
- ✅ Their own submissions only
- ✅ Their own profile

### Teachers See:
- ✅ Assignments they created
- ✅ Submissions from their students only
- ✅ Their students' profiles
- ✅ Their own profile

### Admins See:
- ✅ Everything (all assignments, all submissions, all users)
- ✅ Audit logs
- ✅ System statistics

## 📊 Audit Logging

All actions are logged to the `audit_logs` table:

- **Who**: User ID and role
- **What**: Action type (create_assignment, submit_assignment, etc.)
- **When**: Timestamp
- **RAG Details**: Retrieval chunks used, model called, tokens, cost
- **Metadata**: Additional context

Query audit logs:
```sql
-- Get all assignment creation logs
SELECT * FROM audit_logs WHERE action = 'create_assignment';

-- Get logs for a specific user
SELECT * FROM audit_logs WHERE user_id = 'user-uuid';

-- Get cost estimates
SELECT 
    user_id,
    SUM(cost_estimate) as total_cost,
    COUNT(*) as action_count
FROM audit_logs
WHERE provider = 'openai'
GROUP BY user_id;
```

## 🛡️ RLS Policies

The system uses Supabase Row-Level Security (RLS) to enforce data isolation:

1. **Profiles**: Users see their own profile + related users (teacher/students)
2. **Assignments**: Teachers see their own, students see their teacher's
3. **Submissions**: Students see their own, teachers see their students'
4. **Audit Logs**: Users see their own, admins see all

All policies are defined in `rbac_schema.sql`.

## 🔧 Testing

### Test Teacher Access
```bash
# Get teacher token (from frontend or Supabase auth)
curl -X POST http://localhost:8000/create-assignment \
  -H "Authorization: Bearer <teacher-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Test Topic",
    "description": "Test Description",
    "type": "theoretical",
    "num_questions": 3,
    "section": "CS-101-A"
  }'
```

### Test Student Access
```bash
# Student can only see their teacher's assignments
curl -X GET http://localhost:8000/get-my-assignments \
  -H "Authorization: Bearer <student-token>"
```

### Test Admin Access
```bash
# Admin can see everything
curl -X GET http://localhost:8000/admin/stats \
  -H "Authorization: Bearer <admin-token>"
```

## 🐛 Troubleshooting

### "Authentication required"
- Make sure you're sending the `Authorization: Bearer <token>` header
- Verify the token is valid in Supabase

### "Access denied"
- Check user role in `profiles` table
- Verify RLS policies are enabled
- Check that user has correct role for the endpoint

### "User profile not found"
- Make sure user exists in `profiles` table
- Verify the user_id matches between auth and profiles

### RLS not working
- Ensure RLS is enabled: `ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;`
- Check policies exist: `SELECT * FROM pg_policies WHERE tablename = '<table>';`
- Verify you're using the correct Supabase client (service role for backend)

## 📝 Migration from Old Schema

If you have existing data:

1. **Backup your data**
2. **Run migration script** (create one based on your old schema)
3. **Map old users to new roles**
4. **Assign students to teachers**
5. **Update assignments with section info**

## ✅ Verification Checklist

- [ ] Database schema created
- [ ] RLS policies enabled
- [ ] Test users created (admin, teacher, student)
- [ ] Environment variables set
- [ ] Backend running with RBAC
- [ ] Can create assignment as teacher
- [ ] Can submit as student
- [ ] Can view filtered data
- [ ] Audit logs being created
- [ ] RLS preventing unauthorized access

## 🎯 Next Steps

1. **Frontend Integration**: Update frontend to use new endpoints
2. **Token Management**: Implement proper JWT token handling
3. **File Uploads**: Integrate Supabase Storage for file submissions
4. **Grading**: Add grading endpoints for teachers
5. **Notifications**: Add notification system for assignments

---

**Security Note**: In production, always:
- Use HTTPS
- Validate all inputs
- Rate limit endpoints
- Monitor audit logs
- Regularly review RLS policies
- Use service role key only on backend (never expose to frontend)

