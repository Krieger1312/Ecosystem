-- Схема контент-фабрики. Разворачивается в том же Postgres, отдельной
-- схемой `content`, что и freelance/brain.

CREATE SCHEMA IF NOT EXISTS content;

-- Слой 1: разборы трендов/конкурентов
CREATE TABLE IF NOT EXISTS content.trend_analyses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_url      TEXT NOT NULL,
    platform        TEXT NOT NULL,           -- 'youtube' | 'tiktok'
    analysis        TEXT,                    -- разбор хуков/приёмов от Claude
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Слой 2: идеи/концепции/сценарии
CREATE TABLE IF NOT EXISTS content.ideas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    script          TEXT,
    platform_target TEXT NOT NULL,           -- 'youtube' | 'tiktok' | 'both'
    based_on_trend_id UUID REFERENCES content.trend_analyses(id),
    status          TEXT NOT NULL DEFAULT 'draft', -- 'draft'|'approved'|'rejected'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Слой 3-4: ассеты и финальные видео
CREATE TABLE IF NOT EXISTS content.assets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idea_id         UUID NOT NULL REFERENCES content.ideas(id),
    asset_type      TEXT NOT NULL,           -- 'voiceover' | 'keyed_footage' | 'other'
    file_path       TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS content.videos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idea_id         UUID NOT NULL REFERENCES content.ideas(id),
    file_path       TEXT NOT NULL,
    qa_passed       BOOLEAN,
    qa_notes        TEXT,
    status          TEXT NOT NULL DEFAULT 'draft', -- 'draft'|'ready_to_publish'|'published'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Слой 5: публикации
CREATE TABLE IF NOT EXISTS content.publications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id        UUID NOT NULL REFERENCES content.videos(id),
    platform        TEXT NOT NULL,
    platform_post_id TEXT,                   -- id ролика на площадке, для API-запросов метрик
    published_at    TIMESTAMPTZ
);

-- Слой 6: метрики как временной ряд (вариант Outcome = time_series,
-- см. brain-core/config/ontology_types.yaml)
CREATE TABLE IF NOT EXISTS content.metrics_timeseries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_id  UUID NOT NULL REFERENCES content.publications(id),
    metric_name     TEXT NOT NULL,           -- 'views' | 'retention_pct' | 'ctr' | ...
    value           NUMERIC NOT NULL,
    measured_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_metrics_publication ON content.metrics_timeseries (publication_id);
CREATE INDEX IF NOT EXISTS idx_metrics_measured_at ON content.metrics_timeseries (measured_at);
