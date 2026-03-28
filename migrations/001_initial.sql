-- Initial schema for de_matrix PostgreSQL storage.
-- Use via psql or scripts/db_init.py (SQLAlchemy create_all alternative).

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS domains (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS skills (
    id SERIAL PRIMARY KEY,
    domain_id INTEGER NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_skills_domain_name UNIQUE (domain_id, name)
);

CREATE TABLE IF NOT EXISTS actions (
    id SERIAL PRIMARY KEY,
    skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    template_id VARCHAR(128),
    level_tag VARCHAR(16),
    level_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    leaf_view JSONB NOT NULL DEFAULT '{}'::jsonb,
    review_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    sort_order INTEGER NOT NULL DEFAULT 0
);

ALTER TABLE actions ADD COLUMN IF NOT EXISTS level_tags JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE actions ADD COLUMN IF NOT EXISTS leaf_view JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS subactions (
    id SERIAL PRIMARY KEY,
    action_id INTEGER NOT NULL REFERENCES actions(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    template_id VARCHAR(128),
    level_tag VARCHAR(16),
    level_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    leaf_view JSONB NOT NULL DEFAULT '{}'::jsonb,
    review_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    sort_order INTEGER NOT NULL DEFAULT 0
);

ALTER TABLE subactions ADD COLUMN IF NOT EXISTS level_tags JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE subactions ADD COLUMN IF NOT EXISTS leaf_view JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS action_templates (
    id VARCHAR(128) PRIMARY KEY,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS action_examples (
    id SERIAL PRIMARY KEY,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ui_config (
    id INTEGER PRIMARY KEY,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS stable_state (
    id INTEGER PRIMARY KEY,
    stable_backup_id VARCHAR(64),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS change_requests (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    merge_mode VARCHAR(64) NOT NULL DEFAULT 'append',
    target_domain VARCHAR(255),
    target_skill VARCHAR(255),
    created_by VARCHAR(64) NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS change_revisions (
    id SERIAL PRIMARY KEY,
    change_request_id INTEGER NOT NULL REFERENCES change_requests(id) ON DELETE CASCADE,
    revision_no INTEGER NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    note TEXT NOT NULL DEFAULT '',
    created_by VARCHAR(64) NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_change_revision_no UNIQUE (change_request_id, revision_no)
);

CREATE TABLE IF NOT EXISTS approval_decisions (
    id SERIAL PRIMARY KEY,
    change_request_id INTEGER NOT NULL REFERENCES change_requests(id) ON DELETE CASCADE,
    decision VARCHAR(32) NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    actor VARCHAR(64) NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS change_discussion_threads (
    id SERIAL PRIMARY KEY,
    change_request_id INTEGER NOT NULL REFERENCES change_requests(id) ON DELETE CASCADE,
    subject VARCHAR(255) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    requires_resolution BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(64) NOT NULL DEFAULT 'system',
    created_role VARCHAR(32) NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_by VARCHAR(64),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS change_discussion_messages (
    id SERIAL PRIMARY KEY,
    thread_id INTEGER NOT NULL REFERENCES change_discussion_threads(id) ON DELETE CASCADE,
    author VARCHAR(64) NOT NULL DEFAULT 'system',
    author_role VARCHAR(32) NOT NULL DEFAULT 'user',
    body TEXT NOT NULL DEFAULT '',
    kind VARCHAR(32) NOT NULL DEFAULT 'comment',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notification_logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    subject VARCHAR(255) NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    recipients JSONB NOT NULL DEFAULT '[]'::jsonb,
    context JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_by VARCHAR(64) NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_attempt_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ
);

ALTER TABLE domains ADD COLUMN IF NOT EXISTS code VARCHAR(255);
ALTER TABLE skills ADD COLUMN IF NOT EXISTS code VARCHAR(255);
ALTER TABLE skills ADD COLUMN IF NOT EXISTS responsible VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE skills ADD COLUMN IF NOT EXISTS level_sticker VARCHAR(16);
ALTER TABLE actions ADD COLUMN IF NOT EXISTS code VARCHAR(255);
ALTER TABLE subactions ADD COLUMN IF NOT EXISTS code VARCHAR(255);
ALTER TABLE action_templates ADD COLUMN IF NOT EXISTS name VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE action_templates ADD COLUMN IF NOT EXISTS is_parent BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE action_templates ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';
ALTER TABLE action_examples ADD COLUMN IF NOT EXISTS example_id VARCHAR(128);
ALTER TABLE action_examples ADD COLUMN IF NOT EXISTS title VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE action_examples ADD COLUMN IF NOT EXISTS language VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE action_examples ADD COLUMN IF NOT EXISTS code TEXT NOT NULL DEFAULT '';
ALTER TABLE action_examples ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';
ALTER TABLE change_revisions ADD COLUMN IF NOT EXISTS staging_batch_id INTEGER NULL;

CREATE TABLE IF NOT EXISTS action_review_questions (
    id SERIAL PRIMARY KEY,
    action_id INTEGER NOT NULL REFERENCES actions(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    question TEXT NOT NULL,
    CONSTRAINT uq_action_review_questions_pos UNIQUE (action_id, sort_order)
);

CREATE TABLE IF NOT EXISTS subaction_review_questions (
    id SERIAL PRIMARY KEY,
    subaction_id INTEGER NOT NULL REFERENCES subactions(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    question TEXT NOT NULL,
    CONSTRAINT uq_subaction_review_questions_pos UNIQUE (subaction_id, sort_order)
);

CREATE TABLE IF NOT EXISTS action_template_min_requirements (
    id SERIAL PRIMARY KEY,
    template_id VARCHAR(128) NOT NULL REFERENCES action_templates(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    text TEXT NOT NULL,
    CONSTRAINT uq_template_min_req_pos UNIQUE (template_id, sort_order)
);

CREATE TABLE IF NOT EXISTS action_template_antipatterns (
    id SERIAL PRIMARY KEY,
    template_id VARCHAR(128) NOT NULL REFERENCES action_templates(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    text TEXT NOT NULL,
    CONSTRAINT uq_template_antipattern_pos UNIQUE (template_id, sort_order)
);

CREATE TABLE IF NOT EXISTS action_template_stack_refs (
    id SERIAL PRIMARY KEY,
    template_id VARCHAR(128) NOT NULL REFERENCES action_templates(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    stack_key VARCHAR(128) NOT NULL,
    CONSTRAINT uq_template_stack_ref_pos UNIQUE (template_id, sort_order)
);

CREATE TABLE IF NOT EXISTS action_template_example_refs (
    id SERIAL PRIMARY KEY,
    template_id VARCHAR(128) NOT NULL REFERENCES action_templates(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    example_ref VARCHAR(128) NOT NULL,
    CONSTRAINT uq_template_example_ref_pos UNIQUE (template_id, sort_order)
);

CREATE TABLE IF NOT EXISTS action_template_literature_refs (
    id SERIAL PRIMARY KEY,
    template_id VARCHAR(128) NOT NULL REFERENCES action_templates(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    literature_id VARCHAR(128) NOT NULL,
    CONSTRAINT uq_template_literature_ref_pos UNIQUE (template_id, sort_order)
);

CREATE TABLE IF NOT EXISTS ui_section_titles (
    id SERIAL PRIMARY KEY,
    key VARCHAR(128) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS ui_settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(128) UNIQUE NOT NULL,
    value JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS staging_batches (
    id SERIAL PRIMARY KEY,
    source_filename VARCHAR(255) NOT NULL DEFAULT '',
    merge_mode VARCHAR(64) NOT NULL DEFAULT 'append',
    target_domain VARCHAR(255),
    target_skill VARCHAR(255),
    created_by VARCHAR(64) NOT NULL DEFAULT 'system',
    status VARCHAR(32) NOT NULL DEFAULT 'parsed',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staging_domains (
    id SERIAL PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES staging_batches(id) ON DELETE CASCADE,
    code VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_staging_domain_code UNIQUE (batch_id, code)
);

CREATE TABLE IF NOT EXISTS staging_skills (
    id SERIAL PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES staging_batches(id) ON DELETE CASCADE,
    domain_code VARCHAR(255) NOT NULL,
    code VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    responsible VARCHAR(255) NOT NULL DEFAULT '',
    level_sticker VARCHAR(16),
    sort_order INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_staging_skill_code UNIQUE (batch_id, domain_code, code)
);
ALTER TABLE staging_skills ADD COLUMN IF NOT EXISTS responsible VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE staging_skills ADD COLUMN IF NOT EXISTS level_sticker VARCHAR(16);

CREATE TABLE IF NOT EXISTS staging_actions (
    id SERIAL PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES staging_batches(id) ON DELETE CASCADE,
    skill_code VARCHAR(255) NOT NULL,
    code VARCHAR(255) NOT NULL,
    text TEXT NOT NULL,
    template_id VARCHAR(128),
    level_tag VARCHAR(16),
    level_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    leaf_view JSONB NOT NULL DEFAULT '{}'::jsonb,
    sort_order INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_staging_action_code UNIQUE (batch_id, skill_code, code)
);

ALTER TABLE staging_actions ADD COLUMN IF NOT EXISTS level_tags JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE staging_actions ADD COLUMN IF NOT EXISTS leaf_view JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS staging_subactions (
    id SERIAL PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES staging_batches(id) ON DELETE CASCADE,
    action_code VARCHAR(255) NOT NULL,
    code VARCHAR(255) NOT NULL,
    text TEXT NOT NULL,
    template_id VARCHAR(128),
    level_tag VARCHAR(16),
    level_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    leaf_view JSONB NOT NULL DEFAULT '{}'::jsonb,
    sort_order INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_staging_subaction_code UNIQUE (batch_id, action_code, code)
);

ALTER TABLE staging_subactions ADD COLUMN IF NOT EXISTS level_tags JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE staging_subactions ADD COLUMN IF NOT EXISTS leaf_view JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS staging_action_review_questions (
    id SERIAL PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES staging_batches(id) ON DELETE CASCADE,
    action_code VARCHAR(255) NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    question TEXT NOT NULL,
    CONSTRAINT uq_staging_action_q_pos UNIQUE (batch_id, action_code, sort_order)
);

CREATE TABLE IF NOT EXISTS staging_subaction_review_questions (
    id SERIAL PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES staging_batches(id) ON DELETE CASCADE,
    subaction_code VARCHAR(255) NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    question TEXT NOT NULL,
    CONSTRAINT uq_staging_subaction_q_pos UNIQUE (batch_id, subaction_code, sort_order)
);

ALTER TABLE change_revisions
    DROP CONSTRAINT IF EXISTS fk_change_revisions_staging_batch;
ALTER TABLE change_revisions
    ADD CONSTRAINT fk_change_revisions_staging_batch
    FOREIGN KEY (staging_batch_id) REFERENCES staging_batches(id) ON DELETE SET NULL;

ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS user_presence_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username VARCHAR(64) NOT NULL DEFAULT '',
    session_token VARCHAR(128) UNIQUE NOT NULL,
    ip_address VARCHAR(128) NOT NULL DEFAULT '',
    user_agent VARCHAR(512) NOT NULL DEFAULT '',
    login_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    logout_at TIMESTAMPTZ,
    ended_reason VARCHAR(32) NOT NULL DEFAULT ''
);

