# BACKEND SUBTITLE FORMAT SPECIFICATION

## Обзор

Этот документ определяет формат данных, который backend сервер (использующий `youtube-transcript-api`) должен возвращать расширению при получении субтитров из YouTube.

**Цель**: Обеспечить совместимость backend ответов с существующей архитектурой расширения, где субтитры должны быть обработаны точно в том же формате, как они приходят из YouTube API.

---

## API Endpoint

```
GET /api/subtitles/:videoId
Query Parameters:
  - lang: язык субтитров (например: 'en', 'ru', 'uk', 'de')
  - format: формат ответа ('json' по умолчанию, возможно также 'srt')
```

**Пример запроса**:
```
https://backend.example.com/api/subtitles/dQw4w9WgXcQ?lang=en&format=json
```

---

## JSON Response Format (формат 'json')

### Структура успешного ответа (HTTP 200)

```json
{
  "success": true,
  "status": "completed",
  "videoId": "dQw4w9WgXcQ",
  "language": "en",
  "count": 42,
  "subtitles": [
    {
      "index": 0,
      "start": 0.5,
      "end": 3.2,
      "dur": 2.7,
      "text": "Hello world"
    },
    {
      "index": 1,
      "start": 3.2,
      "end": 5.8,
      "dur": 2.6,
      "text": "This is a subtitle"
    },
    {
      "index": 42,
      "start": 125.4,
      "end": 128.1,
      "dur": 2.7,
      "text": "Final subtitle"
    }
  ]
}
```

### Структура ошибки (HTTP 200 с ошибкой)

```json
{
  "success": false,
  "status": "error",
  "error": "No subtitles found for this video",
  "videoId": "dQw4w9WgXcQ",
  "language": "en",
  "subtitles": []
}
```

### Структура очереди (для async обработки, если требуется)

```json
{
  "success": true,
  "status": "queued",
  "position": 5,
  "queueId": "task-12345",
  "message": "Your request is queued. Please check back in a few seconds.",
  "videoId": "dQw4w9WgXcQ"
}
```

---

## Поля объекта Subtitle

| Поле | Тип | Обязательно | Описание | Примечание |
|------|-----|------------|---------|-----------|
| `index` | number | ✅ да | Порядковый номер субтитра (0-indexed) | Используется для отсортирования если нужно |
| `start` | number | ✅ да | Время начала в секундах (float) | Например: `0.5`, `125.4` |
| `end` | number | ✅ да | Время окончания в секундах (float) | Например: `3.2`, `128.1` |
| `dur` | number | ✅ да | Длительность в секундах (float) | `end - start` |
| `text` | string | ✅ да | Текст субтитра | Чистый текст без HTML |

### Примечания по полям

**`start` и `end`**:
- Должны быть числами (не строками!)
- Точность: до 1 миллисекунды (3+ знака после запятой)
- Формат: `123.456` (не `00:02:03.456`)
- Могут быть целыми числами (`0`, `5`, `125` — это допустимо)

**`dur`** (duration):
- Вычисляется как `end - start`
- Всегда должно быть положительным числом
- Используется для форматирования при отображении

**`text`**:
- Должна быть очищена от HTML тегов
- Переносы строк заменены на пробелы (или оставлены как `\n`)
- **ВАЖНО**: В расширении используется `.textContent` для отображения, поэтому HTML экранирование автоматическое

---

## Top-level Response Fields

| Поле | Тип | Обязательно | Описание |
|------|-----|------------|---------|
| `success` | boolean | ✅ да | Статус успеха операции |
| `status` | string | ✅ да | `"completed"`, `"queued"`, или `"error"` |
| `videoId` | string | ✅ да | YouTube video ID (11 символов) |
| `language` | string | ✅ да | Язык субтитров (ISO 639-1 код) |
| `subtitles` | array | ✅ да | Массив объектов Subtitle |
| `count` | number | ✅ да | Количество субтитров (length of subtitles array) |
| `error` | string | ❌ нет | Сообщение об ошибке (только если success=false) |
| `position` | number | ❌ нет | Позиция в очереди (только если status="queued") |
| `queueId` | string | ❌ нет | ID очереди (только если status="queued") |

---

## HTTP Status Codes

### ✅ 200 OK
Используется для **всех** ответов (успех и ошибка).
- `success: true` — субтитры успешно получены
- `success: false` — видео существует, но нет субтитров на этом языке
- `success: true, status: "queued"` — запрос в очереди

### ❌ 400 Bad Request
Неправильный video ID (не 11 символов) или отсутствует обязательный параметр `lang`.

```json
{
  "success": false,
  "error": "Invalid video ID format. Must be 11 characters."
}
```

### ❌ 404 Not Found
Видео не существует на YouTube.

```json
{
  "success": false,
  "error": "Video not found on YouTube"
}
```

### ❌ 500 Internal Server Error
Ошибка на стороне backend (исключение, проблема с сетью и т.д.).

```json
{
  "success": false,
  "error": "Internal server error: [description]"
}
```

---

## Language Codes

Backend должен поддерживать все языки, которые доступны через `youtube-transcript-api`:

### Популярные коды:
- `en` — английский
- `ru` — русский
- `uk` — украинский
- `de` — немецкий
- `fr` — французский
- `es` — испанский
- `it` — итальянский
- `ja` — японский
- `zh` — китайский (упрощенный)
- `zh-Hans` — китайский (упрощенный вариант 2)
- `pt` — португальский
- `pl` — польский
- `tr` — турецкий

**Замечание**: `youtube-transcript-api` возвращает коды в виде простых строк (`en`, `ru` и т.д.), что соответствует стандарту ISO 639-1.

---

## Интеграция с расширением

### 1. Как расширение использует субтитры

Расширение обрабатывает ответ backend следующим образом:

```javascript
// js/engine/subtitle-engine-class.js:85-263
async getSubtitles(videoId, languageCode = null) {
  // ... код получает субтитры и возвращает объект с таким формата:
  return {
    videoId: videoId,
    subtitles: [        // ← ЭТОТ МАССИВ должен совпадать с вашим `subtitles` из backend
      {
        start: 0.5,
        end: 3.2,
        dur: 2.7,
        text: "Hello world"
      },
      // ... другие субтитры
    ],
    languages: ['en', 'ru', 'de'],  // ← Список доступных языков
    originalLanguage: 'en',
    currentLanguage: 'en',
    isTranslation: false
  };
}
```

### 2. Отображение в UI

```javascript
// js/modules/subtitles-loader.js:138-265
displaySubtitles(result) {
  // Расширение ожидает, что в result.subtitles будет массив с полями:
  // - start (число в секундах)
  // - end (число в секундах)
  // - dur (число в секундах)
  // - text (строка текста)

  // Для форматирования использует:
  const startTime = this.formatTime(result.subtitles[i].start);  // start ДОЛЖНО быть числом!
  const text = this.cleanSubtitleText(result.subtitles[i].text); // text должен быть строкой
}
```

### 3. Кэширование (YTDLPClient)

```javascript
// js/engine/yt-dlp-client.js
class YTDLPClient {
  async getSubtitles(videoId, lang = 'en', format = 'json') {
    // Возвращает ответ backend КАК ЕСТЬ:
    const cacheKey = `${videoId}_${lang}`;
    if (this.subtitlesCache.has(cacheKey)) {
      return this.subtitlesCache.get(cacheKey);  // ← Это будет ваш JSON объект
    }
  }
}
```

---

## Примеры

### Пример 1: Успешный ответ (русские субтитры)

```json
{
  "success": true,
  "status": "completed",
  "videoId": "dQw4w9WgXcQ",
  "language": "ru",
  "count": 3,
  "subtitles": [
    {
      "index": 0,
      "start": 0,
      "end": 2.5,
      "dur": 2.5,
      "text": "Привет, мир!"
    },
    {
      "index": 1,
      "start": 2.5,
      "end": 5.0,
      "dur": 2.5,
      "text": "Это субтитры на русском"
    },
    {
      "index": 2,
      "start": 5.0,
      "end": 7.5,
      "dur": 2.5,
      "text": "Тестируем систему"
    }
  ]
}
```

### Пример 2: Нет субтитров на этом языке

```json
{
  "success": false,
  "status": "error",
  "error": "No subtitles found for language: ja",
  "videoId": "dQw4w9WgXcQ",
  "language": "ja",
  "count": 0,
  "subtitles": []
}
```

### Пример 3: Видео не существует

```json
{
  "success": false,
  "error": "Video not found on YouTube",
  "videoId": "invalid123456"
}
```

---

## Требования к качеству данных

### ✅ Что ДОЛЖНО быть

1. **Все поля должны быть заполнены**
   - `start`, `end`, `dur` — всегда числа, никогда не строки
   - `text` — никогда не пустая строка (хотя бы пробел)
   - `index` — уникальный порядковый номер

2. **Временные коды должны быть точными**
   - Возрастающий порядок: `subtitles[i].start < subtitles[i+1].start`
   - Не должно быть пропусков или перекрытий (опционально, но рекомендуется)

3. **Текст должен быть очищен**
   - Без HTML тегов (`<i>`, `<b>` и т.д.)
   - Без XML сущностей (`&amp;`, `&quot;` и т.д.)
   - Проблемные символы должны быть заменены или убраны

4. **Ответ должен быть валидный JSON**
   - Используй `application/json` Content-Type
   - Все строки в двойных кавычках
   - Никаких trailing commas

### ❌ Что НЕ ДОЛЖНО быть

1. **Строки вместо чисел для времени**
   - ❌ `"start": "0.5"` → ✅ `"start": 0.5`
   - ❌ `"start": "00:00:00.500"` → ✅ `"start": 0.5`

2. **Пустые поля**
   - ❌ `"text": ""` → ✅ `"text": "Some text"` или вообще пропустить субтитр

3. **Лишние поля**
   - Безвредны, но создают лишний трафик
   - Рекомендуется возвращать ТОЛЬКО обязательные поля

4. **Неправильные типы данных**
   - ❌ `"count": "42"` (строка) → ✅ `"count": 42` (число)
   - ❌ `"subtitles": "null"` → ✅ `"subtitles": []` или `"subtitles": [...]`

---

## Производительность и оптимизация

### Размер ответа
- **Типичное видео**: 40-60 субтитров
- **Длинные видео**: до 200+ субтитров
- **Размер JSON**: ~1-5 КБ для типичного видео

### Кэширование
- Расширение кэширует результаты по ключу `${videoId}_${language}`
- Backend может также использовать кэширование, чтобы избежать повторных запросов к YouTube API

### Таймауты
- Клиент (расширение) ждет ответа **до 60 секунд** (`yt-dlp-client.js:19`)
- Если ответ занимает дольше → клиент отменит запрос
- Рекомендуется ответить в течение **5-10 секунд**

---

## Особые случаи

### 1. Видео с автоматическими субтитрами
- ✅ Поддерживается через youtube-transcript-api
- Возвращать как обычные субтитры

### 2. Видео с несколькими дорожками субтитров
- Backend должен вернуть субтитры **ТОЛЬКО** на запрошенном языке
- Параметр `lang` определяет, какой язык вернуть

### 3. Видео без субтитров
- Вернуть `success: false` с `error: "No subtitles found"`
- `subtitles: []` (пустой массив)
- HTTP 200 (не 404!)

### 4. Видео с субтитрами только на одном языке
- Если видео имеет субтитры только на `en`, а запрос на `ru`
- Вернуть ошибку (не пытаться автоматически перевести)
- Код: `success: false`, `error: "Language not available"`

---

## Проверочный список перед запуском

- [ ] API возвращает `success: true/false` для всех случаев
- [ ] Все `start`, `end`, `dur` — числа, не строки
- [ ] `count` совпадает с `subtitles.length`
- [ ] Субтитры отсортированы по времени начала (ascending)
- [ ] `text` содержит только чистый текст (без HTML)
- [ ] Ответ всегда JSON (даже для ошибок)
- [ ] HTTP 200 для успеха и ошибок (не 404/500 для "нет субтитров")
- [ ] `videoId` параметр валидируется (11 символов)
- [ ] `lang` параметр всегда требуется или имеет дефолт
- [ ] Тестирование с расширением (фактический скриншот диагностики)

---

## Ссылки на код расширения

1. **YTDLPClient** (клиент backend):
   - `js/engine/yt-dlp-client.js`
   - Метод: `getSubtitles(videoId, lang, format)`

2. **SubtitlesEngine** (обработка субтитров):
   - `js/engine/subtitle-engine-class.js`
   - Метод: `getSubtitles(videoId, languageCode)`

3. **SubtitlesLoader** (отображение в UI):
   - `js/modules/subtitles-loader.js`
   - Методы: `displaySubtitles()`, `formatTime()`

4. **Config**:
   - `js/core/config.js`
   - `EXTRACTION_METHODS.USE_YT_DLP_BACKEND: true` для включения backend

---

## История версий

| Версия | Дата | Изменения |
|--------|------|-----------|
| 1.0 | 2025-11-14 | Начальная спецификация |

---

## Заметки для разработчика

- Используй `youtube-transcript-api` (Python) или эквивалент для получения субтитров
- Обработай все ошибки gracefully (видео не существует, нет субтитров и т.д.)
- Логируй все запросы для отладки
- Рассмотри использование кэширования (Redis, SQLite и т.д.)
- Протестируй с разными видео (разные языки, длина, типы субтитров)
- Убедись что ответ соответствует этой спецификации

