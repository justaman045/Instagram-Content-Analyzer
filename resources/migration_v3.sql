-- Migration v3: Link Reels to Owners
-- Required for Analyze.py to update specific account priorities

-- 1. Add owner_handle to reels
ALTER TABLE reels 
ADD COLUMN IF NOT EXISTS owner_handle TEXT;

-- 2. Index for fast aggregation
CREATE INDEX IF NOT EXISTS idx_reels_owner 
ON reels (project_id, owner_handle);
