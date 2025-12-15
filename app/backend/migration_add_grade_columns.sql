-- Migration: Add grade columns to submissions table
-- Run this in your Supabase SQL Editor

-- Add grade columns if they don't exist
DO $$ 
BEGIN
    -- Add grade column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'submissions' AND column_name = 'grade'
    ) THEN
        ALTER TABLE submissions ADD COLUMN grade NUMERIC(5, 2);
        RAISE NOTICE 'Added grade column';
    ELSE
        RAISE NOTICE 'grade column already exists';
    END IF;

    -- Add grade_reason column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'submissions' AND column_name = 'grade_reason'
    ) THEN
        ALTER TABLE submissions ADD COLUMN grade_reason TEXT;
        RAISE NOTICE 'Added grade_reason column';
    ELSE
        RAISE NOTICE 'grade_reason column already exists';
    END IF;

    -- Add plagiarism_score column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'submissions' AND column_name = 'plagiarism_score'
    ) THEN
        ALTER TABLE submissions ADD COLUMN plagiarism_score NUMERIC(5, 2);
        RAISE NOTICE 'Added plagiarism_score column';
    ELSE
        RAISE NOTICE 'plagiarism_score column already exists';
    END IF;
END $$;

-- Verify columns were added
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'submissions' 
AND column_name IN ('grade', 'grade_reason', 'plagiarism_score');

