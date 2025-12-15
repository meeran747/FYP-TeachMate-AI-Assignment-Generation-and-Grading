-- ============================================================
-- Migration: Multi-Class System
-- ============================================================
-- This migration adds support for:
-- 1. Classes (subjects/courses)
-- 2. Teacher-Class relationships (many-to-many)
-- 3. Student-Class enrollments (many-to-many)
-- 4. Assignments linked to classes
-- ============================================================

-- ============================================================
-- 1. CREATE CLASSES TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS classes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,                    -- e.g., "Mathematics", "Science", "English"
    code TEXT UNIQUE,                      -- e.g., "MATH-101", "CS-201" (optional)
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_classes_code ON classes(code);

-- ============================================================
-- 2. CREATE TEACHER_CLASS JUNCTION TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS teacher_class (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    teacher_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    class_id UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (teacher_id, class_id)  -- A teacher can only be assigned to a class once
);

CREATE INDEX IF NOT EXISTS idx_teacher_class_teacher_id ON teacher_class(teacher_id);
CREATE INDEX IF NOT EXISTS idx_teacher_class_class_id ON teacher_class(class_id);

-- ============================================================
-- 3. CREATE STUDENT_CLASS JUNCTION TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS student_class (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    class_id UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    enrolled_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (student_id, class_id)  -- A student can only be enrolled in a class once
);

CREATE INDEX IF NOT EXISTS idx_student_class_student_id ON student_class(student_id);
CREATE INDEX IF NOT EXISTS idx_student_class_class_id ON student_class(class_id);

-- ============================================================
-- 4. UPDATE ASSIGNMENTS TABLE TO INCLUDE CLASS_ID
-- ============================================================
-- Add class_id column to assignments (nullable for backward compatibility)
ALTER TABLE assignments
ADD COLUMN IF NOT EXISTS class_id UUID REFERENCES classes(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_assignments_class_id ON assignments(class_id);

-- Note: Existing assignments will have class_id = NULL
-- You may want to migrate existing data by creating classes and linking them

-- ============================================================
-- 5. HELPER FUNCTION: Get students in a class
-- ============================================================
CREATE OR REPLACE FUNCTION get_class_students(class_uuid UUID)
RETURNS TABLE (
    student_id UUID,
    student_name TEXT,
    student_email TEXT,
    enrolled_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.id,
        p.name,
        p.email,
        sc.enrolled_at
    FROM student_class sc
    JOIN profiles p ON sc.student_id = p.id
    WHERE sc.class_id = class_uuid
    ORDER BY p.name;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 6. HELPER FUNCTION: Get teachers of a class
-- ============================================================
CREATE OR REPLACE FUNCTION get_class_teachers(class_uuid UUID)
RETURNS TABLE (
    teacher_id UUID,
    teacher_name TEXT,
    teacher_email TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.id,
        p.name,
        p.email
    FROM teacher_class tc
    JOIN profiles p ON tc.teacher_id = p.id
    WHERE tc.class_id = class_uuid
    ORDER BY p.name;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 7. HELPER FUNCTION: Get classes for a student
-- ============================================================
CREATE OR REPLACE FUNCTION get_student_classes(student_uuid UUID)
RETURNS TABLE (
    class_id UUID,
    class_name TEXT,
    class_code TEXT,
    enrolled_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.name,
        c.code,
        sc.enrolled_at
    FROM student_class sc
    JOIN classes c ON sc.class_id = c.id
    WHERE sc.student_id = student_uuid
    ORDER BY c.name;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 8. HELPER FUNCTION: Get classes for a teacher
-- ============================================================
CREATE OR REPLACE FUNCTION get_teacher_classes(teacher_uuid UUID)
RETURNS TABLE (
    class_id UUID,
    class_name TEXT,
    class_code TEXT,
    student_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.name,
        c.code,
        COUNT(sc.id) as student_count
    FROM teacher_class tc
    JOIN classes c ON tc.class_id = c.id
    LEFT JOIN student_class sc ON sc.class_id = c.id
    WHERE tc.teacher_id = teacher_uuid
    GROUP BY c.id, c.name, c.code
    ORDER BY c.name;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 9. RLS POLICIES FOR CLASSES
-- ============================================================

-- Enable RLS on classes table
ALTER TABLE classes ENABLE ROW LEVEL SECURITY;

-- Teachers can view all classes (they need to see available classes to teach)
CREATE POLICY "teachers_view_all_classes" ON classes
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM profiles 
            WHERE id = auth.uid() AND role = 'teacher'
        ) OR
        EXISTS (
            SELECT 1 FROM profiles 
            WHERE id = auth.uid() AND role = 'admin'
        )
    );

-- Students can view classes they're enrolled in
CREATE POLICY "students_view_enrolled_classes" ON classes
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM student_class sc
            WHERE sc.class_id = classes.id AND sc.student_id = auth.uid()
        )
    );

-- Admins can do everything
CREATE POLICY "admins_manage_classes" ON classes
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM profiles 
            WHERE id = auth.uid() AND role = 'admin'
        )
    );

-- ============================================================
-- 10. RLS POLICIES FOR TEACHER_CLASS
-- ============================================================

ALTER TABLE teacher_class ENABLE ROW LEVEL SECURITY;

-- Teachers can view their own class assignments
CREATE POLICY "teachers_view_own_class_assignments" ON teacher_class
    FOR SELECT USING (teacher_id = auth.uid());

-- Admins can view all
CREATE POLICY "admins_view_all_teacher_class" ON teacher_class
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM profiles 
            WHERE id = auth.uid() AND role = 'admin'
        )
    );

-- ============================================================
-- 11. RLS POLICIES FOR STUDENT_CLASS
-- ============================================================

ALTER TABLE student_class ENABLE ROW LEVEL SECURITY;

-- Students can view their own enrollments
CREATE POLICY "students_view_own_enrollments" ON student_class
    FOR SELECT USING (student_id = auth.uid());

-- Teachers can view enrollments for their classes
CREATE POLICY "teachers_view_class_enrollments" ON student_class
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM teacher_class tc
            WHERE tc.class_id = student_class.class_id AND tc.teacher_id = auth.uid()
        )
    );

-- Admins can view all
CREATE POLICY "admins_view_all_student_class" ON student_class
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM profiles 
            WHERE id = auth.uid() AND role = 'admin'
        )
    );

-- ============================================================
-- VERIFICATION QUERIES
-- ============================================================
-- Run these to verify the migration:

-- SELECT table_name FROM information_schema.tables 
-- WHERE table_schema = 'public' 
-- AND table_name IN ('classes', 'teacher_class', 'student_class');

-- SELECT column_name, data_type 
-- FROM information_schema.columns 
-- WHERE table_name = 'assignments' AND column_name = 'class_id';

