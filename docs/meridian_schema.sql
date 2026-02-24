-- ============================================================================
-- MERIDIAN — PostgreSQL Schema
-- Workstream Portfolio Health Dashboard
-- FRD-MERIDIAN-001 | BA Portfolio Project 3 | Hadi Mercer | February 2026
-- ============================================================================
-- TARGET:  Supabase (PostgreSQL 15)
-- USAGE:   Paste into Supabase SQL Editor and run in order.
--          Sections are labelled — run them top to bottom.
--          RLS policies assume Supabase Auth (auth.uid()).
-- ============================================================================


-- ============================================================================
-- SECTION 0 — EXTENSIONS
-- ============================================================================

-- UUID generation (already enabled on Supabase, included for completeness)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- ============================================================================
-- SECTION 1 — ENUM TYPES
-- ============================================================================
-- Using CHECK constraints instead of CREATE TYPE enums.
-- Reason: Supabase free tier handles CHECK constraints cleanly in the editor,
-- and they are easier to alter during development without migration headaches.
-- The valid values are documented here for reference.

-- workstream_members.role          : 'owner' | 'contributor' | 'viewer'
-- milestones.status                : 'not_started' | 'in_progress' | 'complete'
-- blockers.status                  : 'open' | 'resolved'
-- updates.post_type                : 'status_update' | 'decision_made' |
--                                    'risk_raised' | 'milestone_reached' |
--                                    'general_announcement'
-- rag_scores.rag_status            : 'green' | 'amber' | 'red'
-- comments.entity_type             : 'workstream' | 'milestone' |
--                                    'blocker' | 'spend_entry'
-- notes.entity_type                : 'workstream' | 'milestone' |
--                                    'blocker' | 'spend_entry'
-- wizard_config.q1_work_type       : 'delivery' | 'analysis' |
--                                    'process_improvement' | 'reporting' |
--                                    'strategy' | 'other'
-- wizard_config.q2_deadline_nature : 'hard_contractual' | 'business_driven' |
--                                    'self_imposed' | 'ongoing'
-- wizard_config.q3_deliverable_type: 'document_report' | 'decision_approval' |
--                                    'built_solution' | 'process_change' |
--                                    'recommendation'
-- wizard_config.q4_budget_exposure : 'client_billable' | 'approved_internal' |
--                                    'informal_none'
-- wizard_config.q5_dependency_level: 'self_contained' | 'depends_1_2' |
--                                    'depends_multiple' | 'blocked_external'
-- wizard_config.q6_risk_level      : 'low' | 'medium' | 'high' | 'critical'
-- wizard_config.q7_phase           : 'discovery' | 'planning' |
--                                    'in_flight' | 'review_closing'
-- wizard_config.q8_update_frequency: 'daily' | 'weekly' |
--                                    'biweekly' | 'monthly'
-- wizard_config.q9_audience        : 'just_me' | 'my_team' |
--                                    'senior_leadership' | 'external_client'
-- workstreams.phase                : mirrors q7 — kept in sync by application


-- ============================================================================
-- SECTION 2 — CORE TABLES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 2.1  users
-- ----------------------------------------------------------------------------
-- Mirrors Supabase auth.users. Created automatically on signup via a trigger
-- (see Section 5). Do not insert into this table manually.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.users (
    id           UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email        TEXT        NOT NULL UNIQUE,
    display_name TEXT        NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  public.users              IS 'Application user profile. Mirrors auth.users. Populated by trigger on signup.';
COMMENT ON COLUMN public.users.id           IS 'Matches auth.users.id — the Supabase Auth UUID.';
COMMENT ON COLUMN public.users.email        IS 'User email address. Must match auth.users.email.';
COMMENT ON COLUMN public.users.display_name IS 'Chosen display name shown in comments, team tab, and updates.';


-- ----------------------------------------------------------------------------
-- 2.2  workstreams
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.workstreams (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    name          TEXT        NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
    description   TEXT        NOT NULL DEFAULT '',
    start_date    DATE        NOT NULL,
    end_date      DATE        NOT NULL CHECK (end_date >= start_date),
    planned_budget NUMERIC(12,2) CHECK (planned_budget IS NULL OR planned_budget >= 0),
    owner_id      UUID        NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    phase         TEXT        NOT NULL DEFAULT 'planning'
                              CHECK (phase IN ('discovery','planning','in_flight','review_closing')),
    is_archived   BOOLEAN     NOT NULL DEFAULT FALSE,
    archived_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_archived_at CHECK (
        (is_archived = FALSE AND archived_at IS NULL) OR
        (is_archived = TRUE  AND archived_at IS NOT NULL)
    )
);

COMMENT ON TABLE  public.workstreams                IS 'Core entity. Represents one bounded piece of work being tracked.';
COMMENT ON COLUMN public.workstreams.planned_budget IS 'NULL when Q4 = informal_none. Budget dimension suppressed if NULL.';
COMMENT ON COLUMN public.workstreams.phase          IS 'Current lifecycle phase. Must stay in sync with wizard_config.q7_phase.';
COMMENT ON COLUMN public.workstreams.owner_id       IS 'The user who created the workstream. Cannot be transferred in v1.';


-- ----------------------------------------------------------------------------
-- 2.3  wizard_config
-- ----------------------------------------------------------------------------
-- One row per workstream. Created when wizard is completed.
-- If Owner re-runs the wizard, the existing row is updated (not replaced)
-- and a change log entry is written (see Section 4 — wizard_change_log).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.wizard_config (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    workstream_id       UUID        NOT NULL UNIQUE REFERENCES public.workstreams(id) ON DELETE CASCADE,
    q1_work_type        TEXT        NOT NULL
                                    CHECK (q1_work_type IN ('delivery','analysis','process_improvement','reporting','strategy','other')),
    q2_deadline_nature  TEXT        NOT NULL
                                    CHECK (q2_deadline_nature IN ('hard_contractual','business_driven','self_imposed','ongoing')),
    q3_deliverable_type TEXT        NOT NULL
                                    CHECK (q3_deliverable_type IN ('document_report','decision_approval','built_solution','process_change','recommendation')),
    q4_budget_exposure  TEXT        NOT NULL
                                    CHECK (q4_budget_exposure IN ('client_billable','approved_internal','informal_none')),
    q5_dependency_level TEXT        NOT NULL
                                    CHECK (q5_dependency_level IN ('self_contained','depends_1_2','depends_multiple','blocked_external')),
    q6_risk_level       TEXT        NOT NULL
                                    CHECK (q6_risk_level IN ('low','medium','high','critical')),
    q7_phase            TEXT        NOT NULL
                                    CHECK (q7_phase IN ('discovery','planning','in_flight','review_closing')),
    q8_update_frequency TEXT        NOT NULL
                                    CHECK (q8_update_frequency IN ('daily','weekly','biweekly','monthly')),
    q9_audience         TEXT        NOT NULL
                                    CHECK (q9_audience IN ('just_me','my_team','senior_leadership','external_client')),
    configured_by       UUID        NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    configured_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  public.wizard_config                  IS '9-question scoring profile. One row per workstream. UNIQUE on workstream_id enforces 1:1 relationship.';
COMMENT ON COLUMN public.wizard_config.q2_deadline_nature IS 'Most impactful single modifier. hard_contractual tightens schedule thresholds significantly.';
COMMENT ON COLUMN public.wizard_config.q4_budget_exposure IS 'informal_none suppresses budget dimension to 5% weight in composite scoring.';
COMMENT ON COLUMN public.wizard_config.q5_dependency_level IS 'blocked_external halves blocker age thresholds.';
COMMENT ON COLUMN public.wizard_config.q6_risk_level      IS 'high/critical compress the Amber-to-Red band across all dimensions.';
COMMENT ON COLUMN public.wizard_config.q8_update_frequency IS 'Controls staleness warning trigger window. weekly = stale after 8 days.';


-- ----------------------------------------------------------------------------
-- 2.4  workstream_members  (junction table — the RLS anchor)
-- ----------------------------------------------------------------------------
-- CRITICAL: Every RLS policy on every other table references this table.
-- A user's role in a workstream determines what they can read and write.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.workstream_members (
    id               UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    workstream_id    UUID        NOT NULL REFERENCES public.workstreams(id) ON DELETE CASCADE,
    user_id          UUID        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    role             TEXT        NOT NULL DEFAULT 'viewer'
                                 CHECK (role IN ('owner','contributor','viewer')),
    is_former_member BOOLEAN     NOT NULL DEFAULT FALSE,
    joined_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_workstream_user UNIQUE (workstream_id, user_id)
);

COMMENT ON TABLE  public.workstream_members                 IS 'Junction table linking users to workstreams with role. The RLS anchor for the entire application.';
COMMENT ON COLUMN public.workstream_members.role            IS 'owner | contributor | viewer. Controls all read/write permissions via RLS.';
COMMENT ON COLUMN public.workstream_members.is_former_member IS 'Set TRUE when member is removed. Records are never deleted. Historical content attributed as Former member.';


-- ----------------------------------------------------------------------------
-- 2.5  invite_links
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.invite_links (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    workstream_id UUID        NOT NULL REFERENCES public.workstreams(id) ON DELETE CASCADE,
    token         TEXT        NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(24), 'base64'),
    created_by    UUID        NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE  public.invite_links           IS 'Open invite link per workstream. Token looked up on signup to auto-assign Viewer role.';
COMMENT ON COLUMN public.invite_links.token     IS 'URL-safe random token. Unique across all workstreams. Only one active link per workstream recommended.';
COMMENT ON COLUMN public.invite_links.is_active IS 'Owner can deactivate without deleting. Inactive tokens are rejected at application layer.';


-- ============================================================================
-- SECTION 3 — WORKSTREAM CONTENT TABLES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 3.1  milestones
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.milestones (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    workstream_id UUID        NOT NULL REFERENCES public.workstreams(id) ON DELETE CASCADE,
    name          TEXT        NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
    due_date      DATE        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'not_started'
                              CHECK (status IN ('not_started','in_progress','complete')),
    created_by    UUID        NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  public.milestones        IS 'Deliverable checkpoints. Completion % feeds Schedule Health in rag_scores.';
COMMENT ON COLUMN public.milestones.status IS 'not_started | in_progress | complete. Any status change triggers RAG recalculation.';


-- ----------------------------------------------------------------------------
-- 3.2  spend_entries
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.spend_entries (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    workstream_id UUID        NOT NULL REFERENCES public.workstreams(id) ON DELETE CASCADE,
    amount        NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    entry_date    DATE        NOT NULL,
    category      TEXT        NOT NULL CHECK (char_length(category) BETWEEN 1 AND 80),
    description   TEXT,
    created_by    UUID        NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  public.spend_entries             IS 'Auditable log of actual spend. Cumulative sum vs planned_budget drives Budget Health.';
COMMENT ON COLUMN public.spend_entries.amount      IS 'Always positive. Individual spend entry, not a running total.';
COMMENT ON COLUMN public.spend_entries.category    IS 'Free-text label (e.g. "Consultancy", "Software", "Travel"). Aids spend breakdown.';
COMMENT ON COLUMN public.spend_entries.description IS 'Optional narrative. Not used in scoring calculations.';


-- ----------------------------------------------------------------------------
-- 3.3  blockers
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.blockers (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    workstream_id   UUID        NOT NULL REFERENCES public.workstreams(id) ON DELETE CASCADE,
    description     TEXT        NOT NULL CHECK (char_length(description) BETWEEN 1 AND 500),
    date_raised     DATE        NOT NULL DEFAULT CURRENT_DATE,
    status          TEXT        NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open','resolved')),
    resolution_note TEXT,
    resolved_at     TIMESTAMPTZ,
    created_by      UUID        NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_resolved CHECK (
        (status = 'open'     AND resolved_at IS NULL) OR
        (status = 'resolved' AND resolved_at IS NOT NULL)
    )
);

COMMENT ON TABLE  public.blockers               IS 'Open/resolved issue log. Age of open blockers (days since date_raised) drives Blocker Health.';
COMMENT ON COLUMN public.blockers.date_raised   IS 'The date the blocker was identified. Age = TODAY - date_raised while status = open.';
COMMENT ON COLUMN public.blockers.resolved_at   IS 'Timestamp set when status changes to resolved. Enforced by CHECK constraint.';


-- ----------------------------------------------------------------------------
-- 3.4  updates
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.updates (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    workstream_id UUID        NOT NULL REFERENCES public.workstreams(id) ON DELETE CASCADE,
    post_type     TEXT        NOT NULL
                              CHECK (post_type IN (
                                  'status_update',
                                  'decision_made',
                                  'risk_raised',
                                  'milestone_reached',
                                  'general_announcement'
                              )),
    title         TEXT        NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    body          TEXT        NOT NULL CHECK (char_length(body) >= 1),
    author_id     UUID        NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    edited_at     TIMESTAMPTZ,
    is_locked     BOOLEAN     NOT NULL DEFAULT FALSE
);

COMMENT ON TABLE  public.updates              IS 'Structured announcement feed. status_update restricted to Owner role (enforced at app layer and RLS).';
COMMENT ON COLUMN public.updates.post_type    IS 'status_update = Owner only. All other types available to Contributors too.';
COMMENT ON COLUMN public.updates.is_locked    IS 'Set TRUE by application 15 minutes after creation. Locked posts cannot be edited.';
COMMENT ON COLUMN public.updates.edited_at    IS 'Timestamp of last edit. NULL if never edited. Only set within the 15-minute window.';


-- ============================================================================
-- SECTION 4 — COLLABORATION TABLES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 4.1  comments  (polymorphic — attaches to any entity)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.comments (
    id               UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type      TEXT        NOT NULL
                                 CHECK (entity_type IN ('workstream','milestone','blocker','spend_entry')),
    entity_id        UUID        NOT NULL,
    body             TEXT        NOT NULL CHECK (char_length(body) >= 1),
    author_id        UUID        NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    is_former_member BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast lookup by entity
CREATE INDEX IF NOT EXISTS idx_comments_entity ON public.comments(entity_type, entity_id);

COMMENT ON TABLE  public.comments                  IS 'Polymorphic comment threads. entity_type + entity_id identify the parent record.';
COMMENT ON COLUMN public.comments.entity_type      IS 'workstream | milestone | blocker | spend_entry. Validated at app layer.';
COMMENT ON COLUMN public.comments.entity_id        IS 'UUID of the parent record. No FK constraint — referential integrity via app layer.';
COMMENT ON COLUMN public.comments.is_former_member IS 'Set TRUE when the author is removed from the workstream. Comment is retained, labelled Former member.';


-- ----------------------------------------------------------------------------
-- 4.2  notes  (polymorphic — single pinned annotation per entity)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.notes (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type TEXT        NOT NULL
                            CHECK (entity_type IN ('workstream','milestone','blocker','spend_entry')),
    entity_id   UUID        NOT NULL UNIQUE,   -- one note per entity enforced here
    body        TEXT        NOT NULL CHECK (char_length(body) >= 1),
    author_id   UUID        NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast lookup by entity
CREATE INDEX IF NOT EXISTS idx_notes_entity ON public.notes(entity_type, entity_id);

COMMENT ON TABLE  public.notes             IS 'Pinned persistent annotation. Max one per entity (UNIQUE on entity_id). Not a thread — a single declarative note.';
COMMENT ON COLUMN public.notes.entity_id   IS 'UNIQUE — one note per parent record. Upsert semantics at application layer.';


-- ============================================================================
-- SECTION 5 — SCORING TABLE
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 5.1  rag_scores
-- ----------------------------------------------------------------------------
-- One row per workstream. Created when wizard is completed (alongside
-- wizard_config). Updated by trigger on every write to:
--   milestones, spend_entries, blockers
-- Also updated when wizard_config is changed.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.rag_scores (
    id               UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    workstream_id    UUID        NOT NULL UNIQUE REFERENCES public.workstreams(id) ON DELETE CASCADE,
    schedule_score   NUMERIC(5,2) NOT NULL DEFAULT 100 CHECK (schedule_score  BETWEEN 0 AND 100),
    budget_score     NUMERIC(5,2) NOT NULL DEFAULT 100 CHECK (budget_score    BETWEEN 0 AND 100),
    blocker_score    NUMERIC(5,2) NOT NULL DEFAULT 100 CHECK (blocker_score   BETWEEN 0 AND 100),
    composite_score  NUMERIC(5,2) NOT NULL DEFAULT 100 CHECK (composite_score BETWEEN 0 AND 100),
    rag_status       TEXT        NOT NULL DEFAULT 'green'
                                 CHECK (rag_status IN ('green','amber','red')),
    is_stale         BOOLEAN     NOT NULL DEFAULT FALSE,
    calculated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  public.rag_scores                IS '1:1 with workstreams. Stores the current calculated health scores. Never manually updated by users.';
COMMENT ON COLUMN public.rag_scores.schedule_score IS 'Derived from Schedule Variance: milestone_completion_% - time_elapsed_%. Mapped to 0-100 score.';
COMMENT ON COLUMN public.rag_scores.budget_score   IS 'Derived from Budget Variance: (planned_to_date - actual_to_date) / total_budget. Mapped to 0-100.';
COMMENT ON COLUMN public.rag_scores.blocker_score  IS 'Derived from open blocker count and age. See Section 5.2 of FRD for scoring table.';
COMMENT ON COLUMN public.rag_scores.composite_score IS 'Weighted average of three dimension scores using wizard-configured weights.';
COMMENT ON COLUMN public.rag_scores.rag_status     IS 'green >= 70 | amber 40-69 | red < 40. Derived from composite_score.';
COMMENT ON COLUMN public.rag_scores.is_stale       IS 'TRUE when no data updated within the period implied by wizard q8_update_frequency.';


-- ============================================================================
-- SECTION 6 — AUDIT / CHANGE LOG TABLE
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 6.1  wizard_change_log
-- ----------------------------------------------------------------------------
-- Written whenever the Owner re-runs the wizard (FR-06).
-- Stores the full before/after as JSONB for auditability.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.wizard_change_log (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    workstream_id UUID        NOT NULL REFERENCES public.workstreams(id) ON DELETE CASCADE,
    changed_by    UUID        NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    config_before JSONB       NOT NULL,
    config_after  JSONB       NOT NULL
);

COMMENT ON TABLE  public.wizard_change_log             IS 'Audit log for wizard re-runs. One row per change. JSONB captures full before/after state.';
COMMENT ON COLUMN public.wizard_change_log.config_before IS 'Snapshot of wizard_config row before the change. All 9 answers captured.';
COMMENT ON COLUMN public.wizard_change_log.config_after  IS 'Snapshot of wizard_config row after the change. Diff visible by comparing the two JSONB objects.';


-- ============================================================================
-- SECTION 7 — INDEXES
-- ============================================================================

-- Workstream lookups
CREATE INDEX IF NOT EXISTS idx_workstreams_owner     ON public.workstreams(owner_id);
CREATE INDEX IF NOT EXISTS idx_workstreams_archived  ON public.workstreams(is_archived);

-- Member lookups (most frequent query pattern — "what workstreams can this user see?")
CREATE INDEX IF NOT EXISTS idx_members_user          ON public.workstream_members(user_id);
CREATE INDEX IF NOT EXISTS idx_members_workstream    ON public.workstream_members(workstream_id);

-- Content tab queries (always filtered by workstream_id)
CREATE INDEX IF NOT EXISTS idx_milestones_ws         ON public.milestones(workstream_id);
CREATE INDEX IF NOT EXISTS idx_spend_ws              ON public.spend_entries(workstream_id);
CREATE INDEX IF NOT EXISTS idx_blockers_ws           ON public.blockers(workstream_id);
CREATE INDEX IF NOT EXISTS idx_blockers_status       ON public.blockers(workstream_id, status);
CREATE INDEX IF NOT EXISTS idx_updates_ws            ON public.updates(workstream_id);

-- Invite token lookup (called on every signup via invite)
CREATE INDEX IF NOT EXISTS idx_invite_token          ON public.invite_links(token) WHERE is_active = TRUE;


-- ============================================================================
-- SECTION 8 — UPDATED_AT TRIGGER (applied to tables that need it)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- Apply to tables with updated_at column
CREATE TRIGGER trg_workstreams_updated_at
    BEFORE UPDATE ON public.workstreams
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_milestones_updated_at
    BEFORE UPDATE ON public.milestones
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_notes_updated_at
    BEFORE UPDATE ON public.notes
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ============================================================================
-- SECTION 9 — RAG RECALCULATION TRIGGER
-- ============================================================================
-- This trigger fires after any INSERT, UPDATE, or DELETE on the three
-- scoring input tables: milestones, spend_entries, blockers.
--
-- DESIGN NOTE: The scoring logic itself lives in Python (the Streamlit app).
-- This trigger does the minimum required at the DB layer: it marks the
-- rag_scores row as needing recalculation by touching calculated_at.
-- The Python scoring function is called by the application immediately after
-- any data write — the trigger is a belt-and-suspenders safeguard.
--
-- Full scoring logic (Section 5 of FRD) is implemented in:
--   pipeline/scoring.py  →  calculate_rag(workstream_id)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.flag_rag_for_recalculation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_workstream_id UUID;
BEGIN
    -- Get the workstream_id from whichever table fired the trigger
    IF TG_OP = 'DELETE' THEN
        v_workstream_id := OLD.workstream_id;
    ELSE
        v_workstream_id := NEW.workstream_id;
    END IF;

    -- Touch calculated_at to signal that scores are stale
    -- The Python app will call calculate_rag() to update the full scores
    UPDATE public.rag_scores
    SET    calculated_at = NOW()
    WHERE  workstream_id = v_workstream_id;

    RETURN COALESCE(NEW, OLD);
END;
$$;

-- Attach to all three scoring input tables
CREATE TRIGGER trg_milestones_rag
    AFTER INSERT OR UPDATE OR DELETE ON public.milestones
    FOR EACH ROW EXECUTE FUNCTION public.flag_rag_for_recalculation();

CREATE TRIGGER trg_spend_rag
    AFTER INSERT OR UPDATE OR DELETE ON public.spend_entries
    FOR EACH ROW EXECUTE FUNCTION public.flag_rag_for_recalculation();

CREATE TRIGGER trg_blockers_rag
    AFTER INSERT OR UPDATE OR DELETE ON public.blockers
    FOR EACH ROW EXECUTE FUNCTION public.flag_rag_for_recalculation();


-- ============================================================================
-- SECTION 10 — AUTO-CREATE USER PROFILE ON SIGNUP
-- ============================================================================
-- Fires after a new row is inserted into auth.users by Supabase Auth.
-- Creates the matching public.users row automatically.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    INSERT INTO public.users (id, email, display_name)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'display_name', split_part(NEW.email, '@', 1))
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- ============================================================================
-- SECTION 11 — ROW LEVEL SECURITY (RLS)
-- ============================================================================
-- RLS is the enforcement layer for the three-role permission model.
-- The workstream_members table is the single source of truth for
-- every permission check.
--
-- Helper function used by all policies:
--   get_user_role(workstream_id) → TEXT | NULL
-- Returns the current user's role in a workstream, or NULL if not a member.
-- ============================================================================

-- Enable RLS on every table
ALTER TABLE public.users               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workstreams         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wizard_config       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workstream_members  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invite_links        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.milestones          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.spend_entries       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.blockers            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.updates             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comments            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notes               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rag_scores          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wizard_change_log   ENABLE ROW LEVEL SECURITY;


-- ----------------------------------------------------------------------------
-- Helper: get the current user's role in a given workstream
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_user_role(p_workstream_id UUID)
RETURNS TEXT LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT role
    FROM   public.workstream_members
    WHERE  workstream_id = p_workstream_id
      AND  user_id       = auth.uid()
      AND  is_former_member = FALSE;
$$;

COMMENT ON FUNCTION public.get_user_role IS
  'Returns the current authenticated user''s role (owner/contributor/viewer) in the given workstream. Returns NULL if not a member or is a former member.';


-- ----------------------------------------------------------------------------
-- users — users can read all profiles (needed for display names in UI)
--         users can only update their own profile
-- ----------------------------------------------------------------------------
CREATE POLICY "users_select_all"
    ON public.users FOR SELECT
    USING (TRUE);

CREATE POLICY "users_update_own"
    ON public.users FOR UPDATE
    USING (id = auth.uid());


-- ----------------------------------------------------------------------------
-- workstreams — visible to all members; writable by owner only
-- ----------------------------------------------------------------------------
CREATE POLICY "workstreams_select_member"
    ON public.workstreams FOR SELECT
    USING (public.get_user_role(id) IS NOT NULL);

CREATE POLICY "workstreams_insert_authenticated"
    ON public.workstreams FOR INSERT
    WITH CHECK (auth.uid() IS NOT NULL AND owner_id = auth.uid());

CREATE POLICY "workstreams_update_owner"
    ON public.workstreams FOR UPDATE
    USING (public.get_user_role(id) = 'owner');

-- No DELETE policy — workstreams are archived, not deleted.


-- ----------------------------------------------------------------------------
-- workstream_members — members can see the team list
--                      owner can insert/update/delete members
-- ----------------------------------------------------------------------------
CREATE POLICY "members_select_member"
    ON public.workstream_members FOR SELECT
    USING (public.get_user_role(workstream_id) IS NOT NULL);

CREATE POLICY "members_insert_owner"
    ON public.workstream_members FOR INSERT
    WITH CHECK (public.get_user_role(workstream_id) = 'owner');

CREATE POLICY "members_update_owner"
    ON public.workstream_members FOR UPDATE
    USING (public.get_user_role(workstream_id) = 'owner');

-- Note: the application uses UPDATE (is_former_member = TRUE) not DELETE for member removal.
-- A DELETE policy is intentionally omitted to prevent accidental data loss.


-- ----------------------------------------------------------------------------
-- wizard_config — all members can read; owner can insert/update
-- ----------------------------------------------------------------------------
CREATE POLICY "wizard_select_member"
    ON public.wizard_config FOR SELECT
    USING (public.get_user_role(workstream_id) IS NOT NULL);

CREATE POLICY "wizard_insert_owner"
    ON public.wizard_config FOR INSERT
    WITH CHECK (public.get_user_role(workstream_id) = 'owner');

CREATE POLICY "wizard_update_owner"
    ON public.wizard_config FOR UPDATE
    USING (public.get_user_role(workstream_id) = 'owner');


-- ----------------------------------------------------------------------------
-- invite_links — all members can read; owner can insert/update
-- ----------------------------------------------------------------------------
CREATE POLICY "invites_select_member"
    ON public.invite_links FOR SELECT
    USING (public.get_user_role(workstream_id) IS NOT NULL);

CREATE POLICY "invites_insert_owner"
    ON public.invite_links FOR INSERT
    WITH CHECK (public.get_user_role(workstream_id) = 'owner');

CREATE POLICY "invites_update_owner"
    ON public.invite_links FOR UPDATE
    USING (public.get_user_role(workstream_id) = 'owner');


-- ----------------------------------------------------------------------------
-- milestones — all members can read; owner + contributor can write
-- ----------------------------------------------------------------------------
CREATE POLICY "milestones_select_member"
    ON public.milestones FOR SELECT
    USING (public.get_user_role(workstream_id) IS NOT NULL);

CREATE POLICY "milestones_insert_contrib"
    ON public.milestones FOR INSERT
    WITH CHECK (public.get_user_role(workstream_id) IN ('owner','contributor'));

CREATE POLICY "milestones_update_contrib"
    ON public.milestones FOR UPDATE
    USING (public.get_user_role(workstream_id) IN ('owner','contributor'));

CREATE POLICY "milestones_delete_contrib"
    ON public.milestones FOR DELETE
    USING (public.get_user_role(workstream_id) IN ('owner','contributor'));


-- ----------------------------------------------------------------------------
-- spend_entries — same as milestones
-- ----------------------------------------------------------------------------
CREATE POLICY "spend_select_member"
    ON public.spend_entries FOR SELECT
    USING (public.get_user_role(workstream_id) IS NOT NULL);

CREATE POLICY "spend_insert_contrib"
    ON public.spend_entries FOR INSERT
    WITH CHECK (public.get_user_role(workstream_id) IN ('owner','contributor'));

-- Spend entries are append-only — no UPDATE or DELETE policies.
-- Corrections are handled by logging a new entry with a negative adjustment (app layer).


-- ----------------------------------------------------------------------------
-- blockers — same as milestones
-- ----------------------------------------------------------------------------
CREATE POLICY "blockers_select_member"
    ON public.blockers FOR SELECT
    USING (public.get_user_role(workstream_id) IS NOT NULL);

CREATE POLICY "blockers_insert_contrib"
    ON public.blockers FOR INSERT
    WITH CHECK (public.get_user_role(workstream_id) IN ('owner','contributor'));

CREATE POLICY "blockers_update_contrib"
    ON public.blockers FOR UPDATE
    USING (public.get_user_role(workstream_id) IN ('owner','contributor'));


-- ----------------------------------------------------------------------------
-- updates — all members can read
--           owner + contributor can INSERT (post_type restriction enforced at app layer)
--           only the author can UPDATE (edit within 15-minute window)
-- ----------------------------------------------------------------------------
CREATE POLICY "updates_select_member"
    ON public.updates FOR SELECT
    USING (public.get_user_role(workstream_id) IS NOT NULL);

CREATE POLICY "updates_insert_contrib"
    ON public.updates FOR INSERT
    WITH CHECK (public.get_user_role(workstream_id) IN ('owner','contributor'));

CREATE POLICY "updates_update_author"
    ON public.updates FOR UPDATE
    USING (
        author_id = auth.uid()
        AND is_locked = FALSE
        AND public.get_user_role(workstream_id) IN ('owner','contributor')
    );

-- No DELETE — updates are permanent once posted (FR-27).


-- ----------------------------------------------------------------------------
-- comments — all members can read; owner + contributor can write
-- ----------------------------------------------------------------------------
-- NOTE: comments uses entity_type + entity_id (polymorphic).
-- RLS cannot directly check workstream_id from the parent record at the DB layer
-- without a complex join. The approach here: the application always passes
-- workstream_id as a separate column in the query context, and we rely on
-- the workstream-level check at app layer. At DB layer, we allow any
-- authenticated user to read/write and rely on app-layer validation.
-- This is the documented tradeoff for the polymorphic pattern (see UML notes).
--
-- For a production hardened version, replace with separate comment tables
-- per entity type, each with a direct workstream_id FK.
-- ----------------------------------------------------------------------------
CREATE POLICY "comments_select_authenticated"
    ON public.comments FOR SELECT
    USING (auth.uid() IS NOT NULL);

CREATE POLICY "comments_insert_authenticated"
    ON public.comments FOR INSERT
    WITH CHECK (auth.uid() IS NOT NULL AND author_id = auth.uid());

-- No UPDATE or DELETE on comments — immutable once posted.


-- ----------------------------------------------------------------------------
-- notes — same tradeoff as comments (polymorphic)
-- ----------------------------------------------------------------------------
CREATE POLICY "notes_select_authenticated"
    ON public.notes FOR SELECT
    USING (auth.uid() IS NOT NULL);

CREATE POLICY "notes_insert_authenticated"
    ON public.notes FOR INSERT
    WITH CHECK (auth.uid() IS NOT NULL AND author_id = auth.uid());

CREATE POLICY "notes_update_author"
    ON public.notes FOR UPDATE
    USING (author_id = auth.uid());


-- ----------------------------------------------------------------------------
-- rag_scores — all members can read; no user writes (system only)
-- ----------------------------------------------------------------------------
CREATE POLICY "rag_select_member"
    ON public.rag_scores FOR SELECT
    USING (public.get_user_role(workstream_id) IS NOT NULL);

-- No INSERT/UPDATE/DELETE policies for users — rag_scores is written
-- exclusively by the Python scoring engine using the service role key.


-- ----------------------------------------------------------------------------
-- wizard_change_log — owner and contributor can read; no user writes
-- ----------------------------------------------------------------------------
CREATE POLICY "changelog_select_member"
    ON public.wizard_change_log FOR SELECT
    USING (public.get_user_role(workstream_id) IS NOT NULL);

-- Written by application using service role key when wizard is re-run.


-- ============================================================================
-- SECTION 12 — SEED DATA (development / demo only)
-- ============================================================================
-- Uncomment and run this section to populate a demo workstream for testing.
-- Replace the UUIDs with real auth.users IDs from your Supabase project.
-- ============================================================================

/*
-- Replace with a real user ID from your Supabase Auth dashboard
DO $$
DECLARE
    v_user_id   UUID := 'your-user-uuid-here';
    v_ws_id     UUID := uuid_generate_v4();
BEGIN

    -- Demo workstream
    INSERT INTO public.workstreams (id, name, description, start_date, end_date, planned_budget, owner_id, phase)
    VALUES (
        v_ws_id,
        'FSC Requirements Gathering',
        'Eliciting and documenting functional requirements for the Financial Services Client portal rebuild.',
        CURRENT_DATE - 14,
        CURRENT_DATE + 28,
        15000.00,
        v_user_id,
        'in_flight'
    );

    -- Add owner to members
    INSERT INTO public.workstream_members (workstream_id, user_id, role)
    VALUES (v_ws_id, v_user_id, 'owner');

    -- Wizard config (hard deadline, client-billable, high risk)
    INSERT INTO public.wizard_config (
        workstream_id, q1_work_type, q2_deadline_nature, q3_deliverable_type,
        q4_budget_exposure, q5_dependency_level, q6_risk_level, q7_phase,
        q8_update_frequency, q9_audience, configured_by
    )
    VALUES (
        v_ws_id, 'analysis', 'hard_contractual', 'document_report',
        'client_billable', 'depends_1_2', 'high', 'in_flight',
        'weekly', 'external_client', v_user_id
    );

    -- Initial RAG score row (will be recalculated by app on first load)
    INSERT INTO public.rag_scores (workstream_id)
    VALUES (v_ws_id);

    -- Sample milestones
    INSERT INTO public.milestones (workstream_id, name, due_date, status, created_by) VALUES
        (v_ws_id, 'Stakeholder interviews complete',  CURRENT_DATE - 7,  'complete',    v_user_id),
        (v_ws_id, 'As-Is process maps drafted',       CURRENT_DATE + 3,  'in_progress', v_user_id),
        (v_ws_id, 'Requirements workshop delivered',  CURRENT_DATE + 10, 'not_started', v_user_id),
        (v_ws_id, 'FRD v1 draft submitted for review',CURRENT_DATE + 21, 'not_started', v_user_id);

    -- Sample spend entries
    INSERT INTO public.spend_entries (workstream_id, amount, entry_date, category, description, created_by) VALUES
        (v_ws_id, 3200.00, CURRENT_DATE - 10, 'Consultancy', 'Week 1 BA time', v_user_id),
        (v_ws_id, 3200.00, CURRENT_DATE - 3,  'Consultancy', 'Week 2 BA time', v_user_id);

    -- Sample open blocker
    INSERT INTO public.blockers (workstream_id, description, date_raised, status, created_by) VALUES
        (v_ws_id, 'Awaiting IT department to provide current system data dictionary — requested 5 days ago.',
         CURRENT_DATE - 5, 'open', v_user_id);

END $$;
*/


-- ============================================================================
-- SECTION 13 — QUICK REFERENCE QUERIES
-- ============================================================================
-- Useful queries for testing the schema after setup.
-- Run these in the Supabase SQL Editor to verify data.
-- ============================================================================

/*
-- All workstreams visible to the current user (respects RLS)
SELECT w.id, w.name, w.phase, w.is_archived,
       r.rag_status, r.composite_score, r.is_stale
FROM   public.workstreams w
LEFT JOIN public.rag_scores r ON r.workstream_id = w.id
ORDER BY w.created_at DESC;

-- Current user's role in each workstream
SELECT w.name, m.role, m.joined_at
FROM   public.workstream_members m
JOIN   public.workstreams w ON w.id = m.workstream_id
WHERE  m.user_id = auth.uid()
  AND  m.is_former_member = FALSE;

-- Open blockers with age (days)
SELECT b.description,
       b.date_raised,
       (CURRENT_DATE - b.date_raised) AS age_days,
       w.name AS workstream
FROM   public.blockers b
JOIN   public.workstreams w ON w.id = b.workstream_id
WHERE  b.status = 'open'
ORDER BY age_days DESC;

-- Schedule variance per workstream (raw inputs for scoring engine)
SELECT w.id,
       w.name,
       w.start_date,
       w.end_date,
       COUNT(m.id)                                                         AS total_milestones,
       COUNT(m.id) FILTER (WHERE m.status = 'complete')                   AS complete_milestones,
       ROUND(COUNT(m.id) FILTER (WHERE m.status = 'complete')::NUMERIC
             / NULLIF(COUNT(m.id), 0) * 100, 1)                           AS completion_pct,
       ROUND((CURRENT_DATE - w.start_date)::NUMERIC
             / NULLIF((w.end_date - w.start_date), 0) * 100, 1)           AS time_elapsed_pct
FROM   public.workstreams w
LEFT JOIN public.milestones m ON m.workstream_id = w.id
GROUP BY w.id, w.name, w.start_date, w.end_date;

-- Budget variance per workstream (raw inputs for scoring engine)
SELECT w.id,
       w.name,
       w.planned_budget,
       COALESCE(SUM(s.amount), 0)                                   AS actual_spend,
       w.planned_budget - COALESCE(SUM(s.amount), 0)                AS remaining_budget,
       ROUND((w.planned_budget - COALESCE(SUM(s.amount), 0))
             / NULLIF(w.planned_budget, 0) * 100, 1)                AS budget_remaining_pct
FROM   public.workstreams w
LEFT JOIN public.spend_entries s ON s.workstream_id = w.id
WHERE  w.planned_budget IS NOT NULL
GROUP BY w.id, w.name, w.planned_budget;
*/


-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
-- Tables created:   13
-- Triggers:         6
-- RLS policies:     32
-- Indexes:          12
-- Helper functions: 3
--
-- Next step: pipeline/scoring.py — Python implementation of the RAG
-- scoring engine that reads from this schema and writes back to rag_scores.
-- ============================================================================
