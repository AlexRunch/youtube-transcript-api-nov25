# YouTube Subtitles API Backend

Простой Flask сервер для получения YouTube субтитров через **youtube-transcript-api**.

## 🎯 Что это?

Backend сервер, который позволяет вашему Chrome расширению получать YouTube субтитры даже когда прямой доступ заблокирован.

**Архитектура:**
```
Chrome Extension
    ↓ (POST /api/subtitles)
Railroad Backend (этот сервер)
    ↓ (fetch к YouTube)
YouTube API
    ↓
Субтитры JSON
```

## 📦 Содержимое

- `app.py` — основной Flask сервер (~200 строк кода)
- `requirements.txt` — зависимости Python
- `Procfile` — конфигурация для Railway
- `.env.example` — пример переменных окружения

## 🚀 Локальный запуск (для разработки)

### 1. Установить зависимости

```bash
cd youtube-transcript-api
pip install -r requirements.txt
```

### 2. Запустить сервер

```bash
python app.py
```

Сервер запустится на `http://localhost:5000`

### 3. Тестировать API

**Здоровье:**
```bash
curl http://localhost:5000/api/health
```

**Получить субтитры:**
```bash
curl -X POST http://localhost:5000/api/subtitles \
  -H "Content-Type: application/json" \
  -d '{
    "videoId": "E19_kwN0f38",
    "language": "en",
    "translateTo": null
  }'
```

**Получить доступные языки:**
```bash
curl http://localhost:5000/api/languages/E19_kwN0f38
```

## 📡 API Контракт

### POST /api/subtitles

Получить субтитры видео.

**Request:**
```json
{
  "videoId": "E19_kwN0f38",
  "language": "en",
  "translateTo": null
}
```

**Parameters:**
- `videoId` *(string, required)* — YouTube video ID (11 символов)
- `language` *(string, optional)* — язык субтитров (по умолчанию "en")
- `translateTo` *(string, optional)* — если указан, переводит субтитры на этот язык (например, "ru")

**Response (200 OK):**
```json
{
  "success": true,
  "videoId": "E19_kwN0f38",
  "language": "en",
  "translatedTo": null,
  "subtitles": [
    {
      "time": 0.5,
      "duration": 1.5,
      "text": "Hello world"
    },
    {
      "time": 2.3,
      "duration": 2.1,
      "text": "This is a test"
    }
  ],
  "count": 2,
  "availableLanguages": [
    {
      "code": "en",
      "name": "English",
      "isAuto": false
    }
  ]
}
```

**Error Response (404):**
```json
{
  "success": false,
  "error": "No transcripts available for this video"
}
```

### GET /api/languages/{videoId}

Получить список доступных языков для видео.

**Response:**
```json
{
  "success": true,
  "videoId": "E19_kwN0f38",
  "languages": [
    {
      "code": "en",
      "name": "English",
      "isAuto": false
    },
    {
      "code": "es",
      "name": "Spanish",
      "isAuto": true
    }
  ]
}
```

### GET /api/health

Проверка здоровья сервера.

**Response:**
```json
{
  "ok": true,
  "service": "YouTube Subtitles API",
  "timestamp": "2025-11-12T12:34:56.789012"
}
```

## 🚂 Развертывание на Railway

### Вариант 1: Через Railway CLI (быстро)

```bash
# 1. Установить Railway CLI
# https://docs.railway.app/guides/cli

# 2. Авторизироваться
railway login

# 3. Инициализировать Railway проект
cd youtube-transcript-api
railway init

# 4. Развернуть
railway up
```

### Вариант 2: Через web интерфейс Railway

1. Перейди на https://railway.app
2. Нажми "New Project" → "Deploy from GitHub"
3. Выбери твой репозиторий
4. Укажи папку `/1.DEV/2.DEV_docs/youtube-transcript-api`
5. Railway автоматически:
   - Определит Python проект (по наличию `requirements.txt`)
   - Установит зависимости
   - Запустит `Procfile`

### Переменные окружения на Railway

Railway автоматически установит:
- `PORT` — порт для приложения (не изменяй!)

Если нужны другие переменные, добавь их в Railway dashboard:
```
DEBUG=False
```

### Результат

После развертывания ты получишь URL типа:
```
https://youtube-subtitles-api-production.up.railway.app
```

Проверь здоровье:
```bash
curl https://youtube-subtitles-api-production.up.railway.app/api/health
```

## 🔌 Интеграция с Chrome расширением

В твоем content script добавь:

```javascript
// Адрес Railway сервера (замени на свой)
const API_URL = 'https://youtube-subtitles-api-production.up.railway.app';

async function getSubtitlesFromBackend(videoId, language = 'en') {
  try {
    const response = await fetch(`${API_URL}/api/subtitles`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        videoId: videoId,
        language: language,
        translateTo: null  // или 'ru' для перевода на русский
      })
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const data = await response.json();

    if (data.success) {
      return data.subtitles;
    } else {
      throw new Error(data.error);
    }
  } catch (error) {
    console.error('[BACKEND] Ошибка:', error);
    return null;
  }
}

// Использование:
const subtitles = await getSubtitlesFromBackend('E19_kwN0f38', 'en');
console.log(subtitles);
```

## 📊 Сравнение с текущей системой

| Параметр | yt-dlp (Railway) | youtube-transcript-api (этот) |
|----------|------------------|-------------------------------|
| Скорость | 3-5 сек | 200-400ms |
| Надежность | 70% | 95% |
| Ресурсы | Высокие | Низкие |
| Размер | ~500MB | ~10MB |
| Поддержка перевода | ✅ | ✅ |
| Простота | Сложная | Простая ✅ |
| Стоимость на Railway | $7-15/мес | $0-5/мес |

## 🔧 Troubleshooting

### "No module named 'youtube_transcript_api'"

Переустанови зависимости:
```bash
pip install -r requirements.txt
```

### "Video unavailable"

Это нормально — видео может быть:
- Удалено
- Приватным
- С отключенными субтитрами

### "Transcripts are disabled"

Видео не имеет субтитров. Это видео, где автор отключил комментарии и субтитры.

### Медленный ответ с Railway

Railway может "усыпаться" после неактивности. Это нормально — первый запрос будет медленнее, остальные быстрые.

## 📚 Дополнительно

- **youtube-transcript-api документация:** https://github.com/jdepoix/youtube-transcript-api
- **Railway документация:** https://docs.railway.app
- **Flask документация:** https://flask.palletsprojects.com

## 📝 Лицензия

MIT

## ❓ Вопросы?

Смотри код в `app.py` — там много комментариев!
