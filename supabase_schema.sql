-- ============================================================================
-- Supabase Schema для YouTube Subtitles API Statistics
-- ============================================================================

-- Таблица для дневной статистики
CREATE TABLE IF NOT EXISTS daily_subtitle_api (
    date DATE PRIMARY KEY,
    total_requests INTEGER NOT NULL DEFAULT 0,
    successful INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    languages JSONB DEFAULT '{}',
    error_breakdown JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индекс для быстрого поиска по дате
CREATE INDEX IF NOT EXISTS idx_daily_subtitle_api_date ON daily_subtitle_api(date DESC);

-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для обновления updated_at при изменении строки
DROP TRIGGER IF EXISTS update_daily_subtitle_api_updated_at ON daily_subtitle_api;
CREATE TRIGGER update_daily_subtitle_api_updated_at
    BEFORE UPDATE ON daily_subtitle_api
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Комментарии к таблице и колонкам
COMMENT ON TABLE daily_subtitle_api IS 'Дневная статистика запросов к YouTube Subtitle API';
COMMENT ON COLUMN daily_subtitle_api.date IS 'Дата (YYYY-MM-DD)';
COMMENT ON COLUMN daily_subtitle_api.total_requests IS 'Всего запросов за день';
COMMENT ON COLUMN daily_subtitle_api.successful IS 'Успешных запросов';
COMMENT ON COLUMN daily_subtitle_api.failed IS 'Ошибок';
COMMENT ON COLUMN daily_subtitle_api.languages IS 'Статистика по языкам {"en": 10, "ru": 5}';
COMMENT ON COLUMN daily_subtitle_api.error_breakdown IS 'Статистика по ошибкам {"403": 2, "404": 1}';

-- Включить Row Level Security (для безопасности)
ALTER TABLE daily_subtitle_api ENABLE ROW LEVEL SECURITY;

-- Политика: разрешить все операции для authenticated пользователей
CREATE POLICY "Allow all operations for authenticated users"
ON daily_subtitle_api
FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);

-- Политика: разрешить SELECT для anon пользователей (опционально)
-- Раскомментируйте если хотите публичный доступ к статистике
-- CREATE POLICY "Allow select for anonymous users"
-- ON daily_subtitle_api
-- FOR SELECT
-- TO anon
-- USING (true);
