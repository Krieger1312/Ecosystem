-- Схема ядра brain — общая для всех подсистем.
-- Разворачивается в том же Postgres, что brain-v2, отдельной схемой `brain`.

CREATE SCHEMA IF NOT EXISTS brain;

-- Единая точка подтверждений (Decision Hub, Слой 1)
CREATE TABLE IF NOT EXISTS brain.pending_decisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subsystem       TEXT NOT NULL,           -- 'freelance' | 'content' | 'godot' | ...
    layer           TEXT NOT NULL,           -- доменный слой внутри подсистемы
    stakes          TEXT NOT NULL DEFAULT 'medium', -- 'low' | 'medium' | 'high'
    summary         TEXT NOT NULL,           -- краткое описание для уведомления
    payload         JSONB,                   -- детали, специфичные для подсистемы
    status          TEXT NOT NULL DEFAULT 'pending', -- 'pending'|'approved'|'edited'|'rejected'
    resolution_reason TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pending_decisions_status_stakes
    ON brain.pending_decisions (status, stakes);

-- Лог каждого вызова LLM, для мониторинга бюджета (Слой 2)
CREATE TABLE IF NOT EXISTS brain.llm_usage_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subsystem       TEXT NOT NULL,
    layer           TEXT NOT NULL,
    provider        TEXT NOT NULL,           -- 'anthropic' | 'deepseek' | ...
    model           TEXT NOT NULL,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    estimated_cost_usd NUMERIC,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at ON brain.llm_usage_log (created_at);
CREATE INDEX IF NOT EXISTS idx_llm_usage_subsystem ON brain.llm_usage_log (subsystem);

-- Единый тип Actor (см. docs/ONTOLOGY.md) — здесь только Postgres-зеркало,
-- полноценный граф отношений живёт в Graphiti/Neo4j.
CREATE TABLE IF NOT EXISTS brain.actors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role            TEXT NOT NULL,           -- 'freelance_client' | 'content_viewer' | ...
    external_ref    TEXT,                    -- id во внешней системе, если применимо
    graphiti_node_id TEXT,                   -- связь с узлом в Graphiti
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Результаты прогонов extraction_quality_test.py (Слой 4) — чтобы видеть
-- тренд качества извлечения со временем, а не только последний прогон.
CREATE TABLE IF NOT EXISTS brain.extraction_quality_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sample_size     INTEGER NOT NULL,
    correct_extractions INTEGER NOT NULL,
    accuracy        NUMERIC NOT NULL,        -- correct_extractions / sample_size
    notes           TEXT,
    run_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
