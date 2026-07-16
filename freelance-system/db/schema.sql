-- Схема для системы автоматизации фриланса.
-- Разворачивается в существующем Postgres из brain-v2, отдельной схемой.

CREATE SCHEMA IF NOT EXISTS freelance;

-- Слой 1: обнаруженные вакансии и их скоринг
CREATE TABLE IF NOT EXISTS freelance.jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT NOT NULL,           -- 'upwork_rss', 'freelancer_api', ...
    external_id     TEXT NOT NULL,           -- id вакансии на бирже
    title           TEXT NOT NULL,
    description     TEXT,
    budget_min      NUMERIC,
    budget_max      NUMERIC,
    score           NUMERIC,                 -- 0-10, от score_job.py
    score_reason    TEXT,                    -- почему такой скор
    red_flags       TEXT[],                  -- обнаруженные паттерны риска
    discovered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, external_id)
);

-- Слой 2: сгенерированные и отправленные заявки
CREATE TABLE IF NOT EXISTS freelance.applications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES freelance.jobs(id),
    proposal_text   TEXT NOT NULL,
    confidence      NUMERIC,                 -- уверенность модели в заявке
    auto_sent       BOOLEAN NOT NULL DEFAULT false,
    confirmed_by_user BOOLEAN,               -- NULL пока не решено
    sent_at         TIMESTAMPTZ
);

-- Точки подтверждения и правки на каждом слое (сырые данные для decisions)
CREATE TABLE IF NOT EXISTS freelance.decisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id  UUID REFERENCES freelance.applications(id),
    layer           TEXT NOT NULL,           -- 'proposal' | 'plan' | 'delivery'
    action          TEXT NOT NULL,           -- 'approved' | 'edited' | 'rejected'
    reason          TEXT,                    -- ПОЧЕМУ — это самое ценное поле
    synced_to_graphiti BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Исходы, отслеживаемые через время
CREATE TABLE IF NOT EXISTS freelance.outcomes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id  UUID NOT NULL REFERENCES freelance.applications(id),
    status          TEXT NOT NULL DEFAULT 'pending',
        -- 'pending' | 'won' | 'lost' | 'delivered' | 'client_revision_requested'
    client_satisfaction NUMERIC,             -- 1-5, если применимо
    notes           TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_jobs_score ON freelance.jobs (score DESC);
CREATE INDEX IF NOT EXISTS idx_outcomes_status ON freelance.outcomes (status);
