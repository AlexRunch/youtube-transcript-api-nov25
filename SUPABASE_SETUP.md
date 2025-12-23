# Настройка Supabase для статистики

## Шаг 1: Создайте таблицу в Supabase

1. Зайдите в [Supabase Dashboard](https://app.supabase.com/)
2. Выберите ваш проект (или создайте новый)
3. Перейдите в **SQL Editor** (слева в меню)
4. Скопируйте содержимое файла `supabase_schema.sql`
5. Вставьте в SQL Editor и нажмите **Run**

## Шаг 2: Получите credentials

1. В Supabase Dashboard → **Settings** → **API**
2. Скопируйте:
   - **Project URL** (например: `https://xxxxx.supabase.co`)
   - **anon public** key (начинается с `eyJ...`)

## Шаг 3: Добавьте переменные окружения

### Локально (.env файл):
```bash
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### На Railway:
1. Railway Dashboard → ваш проект → **Variables**
2. Добавьте:
   - `SUPABASE_URL` = ваш Project URL
   - `SUPABASE_KEY` = ваш anon key

## Шаг 4: Перезапустите сервер

Railway автоматически перезапустится после добавления переменных.

## Проверка

После перезапуска:
1. Сделайте запрос к API (получите субтитры)
2. Зайдите в Supabase → **Table Editor** → `daily_stats`
3. Должна появиться строка с сегодняшней статистикой!

## Troubleshooting

**Ошибка "relation daily_stats does not exist":**
- Выполните SQL из `supabase_schema.sql`

**Ошибка "Invalid API key":**
- Проверьте что SUPABASE_KEY правильно скопирован
- Используйте **anon** key, а не service_role key

**Статистика не сохраняется:**
- Проверьте логи Railway на наличие ошибок Supabase
- Убедитесь что RLS политики настроены правильно
