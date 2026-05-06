-- db_init.sql
-- Run this once to set up PostgreSQL schema

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Work Items table (source of truth for incidents)
CREATE TABLE IF NOT EXISTS work_items (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    component_id     TEXT NOT NULL,
    component_type   TEXT NOT NULL,
    priority         TEXT NOT NULL CHECK (priority IN ('P0', 'P1', 'P2')),
    state            TEXT NOT NULL DEFAULT 'OPEN'
                     CHECK (state IN ('OPEN', 'INVESTIGATING', 'RESOLVED', 'CLOSED')),
    start_time       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_time         TIMESTAMPTZ,
    mttr_seconds     FLOAT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- RCA table (linked to Work Items)
CREATE TABLE IF NOT EXISTS rca (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    work_item_id          UUID NOT NULL REFERENCES work_items(id),
    root_cause_category   TEXT NOT NULL,
    problem_description   TEXT NOT NULL,
    fix_applied           TEXT NOT NULL,
    prevention_steps      TEXT NOT NULL,
    submitted_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast priority-based sorting on dashboard
CREATE INDEX IF NOT EXISTS idx_work_items_priority ON work_items(priority, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_rca_work_item ON rca(work_item_id);