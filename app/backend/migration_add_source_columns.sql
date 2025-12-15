-- Add web_sources and academic_sources columns to the submissions table
-- These columns store JSON data with source attribution information
-- This script is idempotent, meaning it can be run multiple times without error
-- if the columns already exist.

DO $$
BEGIN
    -- Add 'web_sources' column if it does not exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='submissions' AND column_name='web_sources') THEN
        ALTER TABLE submissions ADD COLUMN web_sources JSONB;
        RAISE NOTICE 'Column "web_sources" added to "submissions" table.';
    ELSE
        RAISE NOTICE 'Column "web_sources" already exists in "submissions" table.';
    END IF;

    -- Add 'academic_sources' column if it does not exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='submissions' AND column_name='academic_sources') THEN
        ALTER TABLE submissions ADD COLUMN academic_sources JSONB;
        RAISE NOTICE 'Column "academic_sources" added to "submissions" table.';
    ELSE
        RAISE NOTICE 'Column "academic_sources" already exists in "submissions" table.';
    END IF;

END $$;

