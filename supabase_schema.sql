-- ============================================================================
-- Supabase Schema для YouTube Subtitles API Statistics
-- ============================================================================

-- Таблица для дневной статистики
CREATE TABLE IF NOT EXISTS daily_stats (
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
CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_stats(date DESC);

-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для обновления updated_at при изменении строки
DROP TRIGGER IF EXISTS update_daily_stats_updated_at ON daily_stats;
CREATE TRIGGER update_daily_stats_updated_at
    BEFORE UPDATE ON daily_stats
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Комментарии к таблице и колонкам
COMMENT ON TABLE daily_stats IS 'Дневная статистика запросов к YouTube API';
COMMENT ON COLUMN daily_stats.date IS 'Дата (YYYY-MM-DD)';
COMMENT ON COLUMN daily_stats.total_requests IS 'Всего запросов за день';
COMMENT ON COLUMN daily_stats.successful IS 'Успешных запросов';
COMMENT ON COLUMN daily_stats.failed IS 'Ошибок';
COMMENT ON COLUMN daily_stats.languages IS 'Статистика по языкам {"en": 10, "ru": 5}';
COMMENT ON COLUMN daily_stats.error_breakdown IS 'Статистика по ошибкам {"403": 2, "404": 1}';

-- Включить Row Level Security (для безопасности)
ALTER TABLE daily_stats ENABLE ROW LEVEL SECURITY;

-- Политика: разрешить все операции для authenticated пользователей
CREATE POLICY "Allow all operations for authenticated users"
ON daily_stats
FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);

-- Политика: разрешить SELECT для anon пользователей (опционально)
-- Раскомментируйте если хотите публичный доступ к статистике
-- CREATE POLICY "Allow select for anonymous users"
-- ON daily_stats
-- FOR SELECT
-- TO anon
-- USING (true);
