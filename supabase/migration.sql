-- Migration: Crear tabla de datasets para el backend DuckFlow
-- Ejecutar en el SQL Editor de Supabase

CREATE TABLE IF NOT EXISTS datasets (
    id                       TEXT PRIMARY KEY,
    name                     TEXT NOT NULL,
    parquet_path             TEXT NOT NULL,
    total_rows               BIGINT,
    total_features           INTEGER,
    columns_json             TEXT,
    numeric_columns_json     TEXT,
    categorical_columns_json TEXT,
    datetime_columns_json    TEXT,
    missing_total            BIGINT,
    duplicates               BIGINT,
    memory_kb                DOUBLE PRECISION,
    created_at               TIMESTAMP DEFAULT NOW()
);

-- Opcional: política de seguridad para permitir acceso anónimo
ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow anonymous read" ON datasets FOR SELECT USING (true);
CREATE POLICY "Allow anonymous insert" ON datasets FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow anonymous update" ON datasets FOR UPDATE USING (true);
CREATE POLICY "Allow anonymous delete" ON datasets FOR DELETE USING (true);
