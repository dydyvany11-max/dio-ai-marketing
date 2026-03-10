-- PostgreSQL schema for SMM + infographic reporting
-- Assumes: CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Core
CREATE TABLE IF NOT EXISTS workspaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name text NOT NULL,
  description text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Social accounts
CREATE TABLE IF NOT EXISTS social_accounts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  platform text NOT NULL CHECK (platform IN ('vk','telegram')),
  external_id text NOT NULL,
  display_name text,
  access_token bytea,
  token_expires_at timestamptz,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (platform, external_id)
);

-- Audience analysis
CREATE TABLE IF NOT EXISTS audience_reports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  platform text NOT NULL CHECK (platform IN ('vk','telegram')),
  source_id text NOT NULL,
  summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  clusters_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  competitors_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Content generation
CREATE TABLE IF NOT EXISTS content_briefs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  topic text NOT NULL,
  tone text,
  prompt text,
  knowledge_base_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS generated_content (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  brief_id uuid NOT NULL REFERENCES content_briefs(id) ON DELETE CASCADE,
  content_type text NOT NULL CHECK (content_type IN ('text','image','video_script')),
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  platform_variant text,
  quality_score numeric(5,2),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Posts and scheduling
CREATE TABLE IF NOT EXISTS post_drafts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  platform text NOT NULL CHECK (platform IN ('vk','telegram')),
  source_id text NOT NULL,
  content_id uuid NOT NULL REFERENCES generated_content(id) ON DELETE CASCADE,
  scheduled_at timestamptz,
  status text NOT NULL DEFAULT 'draft',
  external_post_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Account reports
CREATE TABLE IF NOT EXISTS account_reports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  platform text NOT NULL CHECK (platform IN ('vk','telegram')),
  source_id text NOT NULL,
  period_from date NOT NULL,
  period_to date NOT NULL,
  metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  best_posts_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Trend snapshots
CREATE TABLE IF NOT EXISTS trend_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  platform text NOT NULL CHECK (platform IN ('vk','telegram')),
  keywords_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  mentions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Infographic reporting (datasets and charts)
CREATE TABLE IF NOT EXISTS reports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title text NOT NULL,
  description text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS datasets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  name text NOT NULL,
  schema_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  data_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS charts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id uuid NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  dataset_id uuid REFERENCES datasets(id) ON DELETE SET NULL,
  chart_type text NOT NULL,
  config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_social_accounts_project ON social_accounts(project_id);
CREATE INDEX IF NOT EXISTS idx_audience_reports_project ON audience_reports(project_id);
CREATE INDEX IF NOT EXISTS idx_post_drafts_project ON post_drafts(project_id);
CREATE INDEX IF NOT EXISTS idx_account_reports_project ON account_reports(project_id);
CREATE INDEX IF NOT EXISTS idx_reports_project ON reports(project_id);
