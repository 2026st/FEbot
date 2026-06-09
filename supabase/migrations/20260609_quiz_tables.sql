-- IPA quiz storage (separate from corpus_* RAG tables)
-- Apply via Supabase SQL Editor or supabase db push

-- Exams metadata
CREATE TABLE IF NOT EXISTS quiz_exams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_id TEXT NOT NULL,
    kamoku TEXT NOT NULL CHECK (kamoku IN ('A', 'B')),
    exam_format TEXT NOT NULL DEFAULT 'cbt',
    source_page_url TEXT,
    source_pdf_qs_url TEXT,
    source_pdf_ans_url TEXT,
    content_version TEXT,
    ingested_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (exam_id, kamoku)
);

-- One row per question (no vector embedding — not mixed into RAG)
CREATE TABLE IF NOT EXISTS quiz_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_uuid UUID NOT NULL REFERENCES quiz_exams(id) ON DELETE CASCADE,
    qid TEXT NOT NULL UNIQUE,
    question_number INT NOT NULL,
    category TEXT NOT NULL,
    field TEXT DEFAULT '',
    body TEXT NOT NULL,
    choices JSONB NOT NULL DEFAULT '[]'::jsonb,
    correct TEXT NOT NULL,
    explanation TEXT NOT NULL DEFAULT '',
    assets JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags TEXT[] NOT NULL DEFAULT '{}',
    source_type TEXT NOT NULL DEFAULT 'ipa_official',
    content_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_quiz_questions_category ON quiz_questions(category);
CREATE INDEX IF NOT EXISTS idx_quiz_questions_tags ON quiz_questions USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_quiz_questions_exam_uuid ON quiz_questions(exam_uuid);

-- Storage bucket for figure screenshots (create in Dashboard if SQL fails)
INSERT INTO storage.buckets (id, name, public)
VALUES ('quiz-assets', 'quiz-assets', true)
ON CONFLICT (id) DO NOTHING;

-- RLS: anon can read quiz data; writes via service_role only
ALTER TABLE quiz_exams ENABLE ROW LEVEL SECURITY;
ALTER TABLE quiz_questions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS quiz_exams_select_anon ON quiz_exams;
CREATE POLICY quiz_exams_select_anon ON quiz_exams
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS quiz_questions_select_anon ON quiz_questions;
CREATE POLICY quiz_questions_select_anon ON quiz_questions
    FOR SELECT TO anon, authenticated USING (true);

-- Storage: public read for quiz-assets
DROP POLICY IF EXISTS quiz_assets_public_read ON storage.objects;
CREATE POLICY quiz_assets_public_read ON storage.objects
    FOR SELECT TO anon, authenticated
    USING (bucket_id = 'quiz-assets');
