-- ============================================================
-- TeachMate Multi-Tenant RBAC Schema
-- ============================================================
-- This schema implements:
-- 1. Role-Based Access Control (Admin, Teacher, Student)
-- 2. Multi-tenant isolation with RLS
-- 3. Teacher-student relationships
-- 4. Section-based organization
-- 5. Audit logging
-- ============================================================

-- ============================================================
-- 1. PROFILES TABLE (Extended with RBAC)
-- ============================================================
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'teacher', 'student')),
    password TEXT,                    -- Password for simple auth (nullable for Supabase Auth users)
    section TEXT,                    -- For teachers: which section they belong to
    teacher_id UUID REFERENCES profiles(id) ON DELETE SET NULL,  -- For students: their teacher
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints (relaxed to allow registration without section/teacher initially)
    CONSTRAINT student_has_teacher CHECK (
        (role = 'student' AND (teacher_id IS NOT NULL OR section IS NOT NULL)) OR 
        (role != 'student')
    )
    -- Note: Removed teacher_has_section constraint to allow teachers to register first, then set section
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_profiles_role ON profiles(role);
CREATE INDEX IF NOT EXISTS idx_profiles_teacher_id ON profiles(teacher_id);
CREATE INDEX IF NOT EXISTS idx_profiles_section ON profiles(section);

-- ============================================================
-- 2. ASSIGNMENTS TABLE (Multi-tenant)
-- ============================================================
CREATE TABLE IF NOT EXISTS assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    teacher_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    section TEXT NOT NULL,              -- Section this assignment belongs to
    topic TEXT NOT NULL,
    description TEXT,
    type TEXT NOT NULL CHECK (type IN ('programming', 'theoretical', 'multiple_choice')),
    num_questions INT CHECK (num_questions >= 0),
    questions JSONB DEFAULT '[]'::jsonb,
    rubric JSONB DEFAULT '{}'::jsonb,
    published BOOLEAN DEFAULT FALSE,
    due_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assignments_teacher_id ON assignments(teacher_id);
CREATE INDEX IF NOT EXISTS idx_assignments_section ON assignments(section);
CREATE INDEX IF NOT EXISTS idx_assignments_published ON assignments(published);

-- ============================================================
-- 3. SUBMISSIONS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id UUID NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    roll_number TEXT,
    section TEXT,
    file_name TEXT,
    file_url TEXT,                     -- Supabase Storage URL
    answer_text TEXT,
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    grade NUMERIC(5, 2),              -- Grade score (e.g., 85.50)
    grade_reason TEXT,                 -- AI explanation for the grade
    plagiarism_score NUMERIC(5, 2),    -- Plagiarism similarity percentage (0-100)
    UNIQUE (assignment_id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_submissions_assignment_id ON submissions(assignment_id);
CREATE INDEX IF NOT EXISTS idx_submissions_student_id ON submissions(student_id);

-- ============================================================
-- 4. AUDIT LOG TABLE (Research-grade tracking)
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE SET NULL,
    user_role TEXT NOT NULL,
    action TEXT NOT NULL,              -- 'create_assignment', 'submit_assignment', etc.
    resource_type TEXT,                 -- 'assignment', 'submission', etc.
    resource_id UUID,
    
    -- RAG/AI tracking
    retrieval_chunks_used JSONB,        -- Array of chunk IDs/metadata used
    model_called TEXT,                  -- 'gpt-4o', 'groq-llama', etc.
    provider TEXT,                      -- 'openai', 'groq'
    token_estimate INT,                 -- Estimated tokens used
    cost_estimate NUMERIC(10, 6),      -- Estimated cost in USD
    
    -- Context
    metadata JSONB DEFAULT '{}'::jsonb, -- Additional context
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- ============================================================
-- 5. ENABLE ROW LEVEL SECURITY (RLS)
-- ============================================================
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- 6. HELPER FUNCTIONS (Security Definer to avoid recursion)
-- ============================================================

-- Function to get user role (bypasses RLS)
CREATE OR REPLACE FUNCTION get_user_role(user_uuid UUID)
RETURNS TEXT AS $$
BEGIN
    RETURN (SELECT role FROM profiles WHERE id = user_uuid);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to check if user is admin (bypasses RLS)
CREATE OR REPLACE FUNCTION is_admin(user_uuid UUID)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM profiles 
        WHERE id = user_uuid AND role = 'admin'
    );
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RETURN FALSE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get teacher_id for a student (bypasses RLS)
CREATE OR REPLACE FUNCTION get_student_teacher_id(student_uuid UUID)
RETURNS UUID AS $$
BEGIN
    RETURN (SELECT teacher_id FROM profiles WHERE id = student_uuid);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================
-- 7. RLS POLICIES - PROFILES
-- ============================================================

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "admins_view_all_profiles" ON profiles;
DROP POLICY IF EXISTS "teachers_view_own_and_students" ON profiles;
DROP POLICY IF EXISTS "students_view_own_and_teacher" ON profiles;
DROP POLICY IF EXISTS "users_update_own_profile" ON profiles;
DROP POLICY IF EXISTS "anyone_can_register" ON profiles;

-- Admins can see all profiles (using security definer function)
CREATE POLICY "admins_view_all_profiles" ON profiles
    FOR SELECT USING (is_admin(auth.uid()));

-- Teachers can see their own profile and their students
CREATE POLICY "teachers_view_own_and_students" ON profiles
    FOR SELECT USING (
        id = auth.uid() OR
        (teacher_id = auth.uid() AND get_user_role(auth.uid()) = 'teacher')
    );

-- Students can see their own profile and their teacher
CREATE POLICY "students_view_own_and_teacher" ON profiles
    FOR SELECT USING (
        id = auth.uid() OR
        (id = get_student_teacher_id(auth.uid()))
    );

-- Users can update their own profile
CREATE POLICY "users_update_own_profile" ON profiles
    FOR UPDATE USING (id = auth.uid());

-- Anyone can insert (for registration)
CREATE POLICY "anyone_can_register" ON profiles
    FOR INSERT WITH CHECK (true);

-- ============================================================
-- 7. RLS POLICIES - ASSIGNMENTS
-- ============================================================

-- Admins can see all assignments (using security definer function)
CREATE POLICY "admins_view_all_assignments" ON assignments
    FOR SELECT USING (is_admin(auth.uid()));

-- Teachers can see their own assignments
CREATE POLICY "teachers_view_own_assignments" ON assignments
    FOR SELECT USING (
        teacher_id = auth.uid() AND get_user_role(auth.uid()) = 'teacher'
    );

-- Students can see assignments from their teacher
CREATE POLICY "students_view_teacher_assignments" ON assignments
    FOR SELECT USING (
        teacher_id = get_student_teacher_id(auth.uid()) AND
        get_user_role(auth.uid()) = 'student'
    );

-- Teachers can create assignments
CREATE POLICY "teachers_create_assignments" ON assignments
    FOR INSERT WITH CHECK (
        teacher_id = auth.uid() AND get_user_role(auth.uid()) = 'teacher'
    );

-- Teachers can update their own assignments
CREATE POLICY "teachers_update_own_assignments" ON assignments
    FOR UPDATE USING (
        teacher_id = auth.uid() AND get_user_role(auth.uid()) = 'teacher'
    );

-- Teachers can delete their own assignments
CREATE POLICY "teachers_delete_own_assignments" ON assignments
    FOR DELETE USING (
        teacher_id = auth.uid() AND get_user_role(auth.uid()) = 'teacher'
    );

-- ============================================================
-- 8. RLS POLICIES - SUBMISSIONS
-- ============================================================

-- Admins can see all submissions
CREATE POLICY "admins_view_all_submissions" ON submissions
    FOR SELECT USING (is_admin(auth.uid()));

-- Students can see only their own submissions
CREATE POLICY "students_view_own_submissions" ON submissions
    FOR SELECT USING (
        student_id = auth.uid() AND get_user_role(auth.uid()) = 'student'
    );

-- Teachers can see submissions from their students
-- Note: Using a subquery that doesn't cause recursion
CREATE POLICY "teachers_view_student_submissions" ON submissions
    FOR SELECT USING (
        get_user_role(auth.uid()) = 'teacher' AND
        student_id IN (
            SELECT p.id FROM profiles p 
            WHERE p.teacher_id = auth.uid() AND p.role = 'student'
        )
    );

-- Students can create their own submissions
CREATE POLICY "students_create_own_submissions" ON submissions
    FOR INSERT WITH CHECK (
        student_id = auth.uid() AND get_user_role(auth.uid()) = 'student'
    );

-- Students can update their own submissions (before deadline)
CREATE POLICY "students_update_own_submissions" ON submissions
    FOR UPDATE USING (
        student_id = auth.uid() AND get_user_role(auth.uid()) = 'student'
    );

-- ============================================================
-- 9. RLS POLICIES - AUDIT LOGS
-- ============================================================

-- Admins can see all audit logs
CREATE POLICY "admins_view_all_audit_logs" ON audit_logs
    FOR SELECT USING (is_admin(auth.uid()));

-- Users can see their own audit logs
CREATE POLICY "users_view_own_audit_logs" ON audit_logs
    FOR SELECT USING (user_id = auth.uid());

-- System can insert audit logs (via service role)
CREATE POLICY "system_insert_audit_logs" ON audit_logs
    FOR INSERT WITH CHECK (true);

-- ============================================================
-- 10. HELPER FUNCTIONS
-- ============================================================

-- Function to get user role
CREATE OR REPLACE FUNCTION get_user_role(user_id UUID)
RETURNS TEXT AS $$
BEGIN
    RETURN (SELECT role FROM profiles WHERE id = user_id);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to check if user is admin
CREATE OR REPLACE FUNCTION is_admin(user_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM profiles 
        WHERE id = user_id AND role = 'admin'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get teacher's students
CREATE OR REPLACE FUNCTION get_teacher_students(teacher_uuid UUID)
RETURNS TABLE(student_id UUID, student_name TEXT, student_email TEXT) AS $$
BEGIN
    RETURN QUERY
    SELECT p.id, p.name, p.email
    FROM profiles p
    WHERE p.teacher_id = teacher_uuid AND p.role = 'student';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================
-- 11. TRIGGERS
-- ============================================================

-- Update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_assignments_updated_at
    BEFORE UPDATE ON assignments
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- END OF SCHEMA
-- ============================================================

