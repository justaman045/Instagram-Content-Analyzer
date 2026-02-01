-- Migration v2: Scalable Monitoring
-- Adds tracking columns for smart scheduling

-- 1. Add last_checked_at
ALTER TABLE monitored_accounts 
ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ DEFAULT NOW();

-- 2. Add check_frequency (hours)
-- Default 6 hours (Regular check)
ALTER TABLE monitored_accounts 
ADD COLUMN IF NOT EXISTS check_frequency INT DEFAULT 6;

-- 3. Add priority_score
-- Higher is more important. 1.0 = normal.
ALTER TABLE monitored_accounts 
ADD COLUMN IF NOT EXISTS priority_score FLOAT DEFAULT 1.0;

-- 4. Index for fast sorting/filtering
CREATE INDEX IF NOT EXISTS idx_monitor_schedule 
ON monitored_accounts (is_active, last_checked_at);
