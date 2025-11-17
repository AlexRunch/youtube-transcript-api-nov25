# YouTube Subtitles API - Integration Guide для Extension 2
## YouTube Description Generator + Title & Chapters

---

## 📋 Оглавление
1. [Быстрый старт](#быстрый-старт)
2. [API Endpoint](#api-endpoint)
3. [Полная документация](#полная-документация)
4. [Примеры кода](#примеры-кода)
5. [Обработка ошибок](#обработка-ошибок)
6. [Тестирование](#тестирование)
7. [Отладка](#отладка)
8. [FAQ](#faq)
9. [Support](#support)

---

## 🚀 Быстрый старт

### За 2 минуты до работающей интеграции:

```javascript
// 1. Функция для получения субтитров
async function getYouTubeSubtitles(videoId) {
  const url = `https://web-production-bd8bb.up.railway.app/api/subtitles/${videoId}?lang=en`;

  const response = await fetch(url);
  const data = await response.json();

  if (!data.success) {
    throw new Error(data.error);
  }

  return data.subtitles;
}

// 2. Использование
const subtitles = await getYouTubeSubtitles('dQw4w9WgXcQ');
console.log(`Получено ${subtitles.length} субтитров`);
console.log(subtitles[0]); // Первый субтитр
```

Вот и все! 🎉

---

## 🔗 API Endpoint

### HTTP Method
```
GET /api/subtitles/<videoId>
```

### Base URL
```
https://web-production-bd8bb.up.railway.app
```

### Parameters

| Параметр | Тип | Обязательный | Описание |
|----------|-----|-------------|---------|
| `videoId` | string | ✅ Да | YouTube video ID (11 символов) |
| `lang` | string | ❌ Нет | **Игнорируется!** API всегда возвращает оригинальный язык видео |
| `format` | string | ❌ Нет | `json` (только этот формат поддерживается) |

### Примеры URL

```bash
# Базовый запрос
https://web-production-bd8bb.up.railway.app/api/subtitles/dQw4w9WgXcQ

# С параметрами (lang игнорируется)
https://web-production-bd8bb.up.railway.app/api/subtitles/dQw4w9WgXcQ?lang=en
https://web-production-bd8bb.up.railway.app/api/subtitles/fi7GI4hyIJc?lang=ru&format=json
```

---

## 📚 Полная документация

### ✅ Success Response (HTTP 200)

```json
{
  "success": true,
  "status": "completed",
  "videoId": "dQw4w9WgXcQ",
  "language": "en",
  "count": 61,
  "subtitles": [
    {
      "index": 0,
      "start": 1.36,
      "end": 3.04,
      "dur": 1.68,
      "text": "[♪♪♪]"
    },
    {
      "index": 1,
      "start": 3.04,
      "end": 5.72,
      "dur": 2.68,
      "text": "♪ Never gonna give you up ♪"
    }
  ]
}
```

### Поле Subtitle Object

| Поле | Тип | Описание | Пример |
|------|-----|---------|--------|
| `index` | number | Порядковый номер (начиная с 0) | `0`, `1`, `42` |
| `start` | number | Время начала в секундах (float) | `1.36`, `3.04` |
| `end` | number | Время окончания в секундах (float) | `3.04`, `5.72` |
| `dur` | number | Длительность (end - start) | `1.68`, `2.68` |
| `text` | string | Текст субтитра (plain text, без HTML) | `"Never gonna give you up"` |

### ❌ Error Response (HTTP 200 с success: false)

#### Видео существует, но нет субтитров
```json
{
  "success": false,
  "status": "error",
  "error": "No subtitles available for this video",
  "videoId": "dQw4w9WgXcQ",
  "language": null,
  "count": 0,
  "subtitles": []
}
```

#### Видео недоступно (HTTP 404)
```json
{
  "success": false,
  "status": "error",
  "error": "Video not found on YouTube",
  "videoId": "invalid"
}
```

#### Неверный format video ID (HTTP 400)
```json
{
  "success": false,
  "status": "error",
  "error": "Invalid video ID format. Must be 11 characters.",
  "videoId": "invalid"
}
```

---

## 💻 Примеры кода

### JavaScript (Vanilla)

```javascript
/**
 * Получить субтитры YouTube видео
 * @param {string} videoId - YouTube video ID (11 символов)
 * @returns {Promise<Array>} Массив субтитров с полями: index, start, end, dur, text
 * @throws {Error} Если видео не найдено или нет субтитров
 */
async function getYouTubeSubtitles(videoId) {
  const API_URL = 'https://web-production-bd8bb.up.railway.app';
  const url = `${API_URL}/api/subtitles/${videoId}`;

  try {
    const response = await fetch(url);
    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || 'Unknown error');
    }

    return data.subtitles;
  } catch (error) {
    console.error('Error fetching subtitles:', error);
    throw error;
  }
}

// Использование
(async () => {
  try {
    const subtitles = await getYouTubeSubtitles('dQw4w9WgXcQ');
    console.log(`Получено ${subtitles.length} субтитров`);

    // Вывести первые 3 субтитра
    subtitles.slice(0, 3).forEach(sub => {
      console.log(`[${sub.start.toFixed(2)}s] ${sub.text}`);
    });
  } catch (error) {
    console.error('Failed to get subtitles:', error.message);
  }
})();
```

### JavaScript (Chrome Extension - Content Script)

```javascript
/**
 * Извлечь YouTube video ID из текущей страницы
 * @returns {string|null} Video ID или null если не на странице видео
 */
function getVideoIdFromPage() {
  // Метод 1: из URL
  const urlParams = new URLSearchParams(window.location.search);
  const videoId = urlParams.get('v');

  if (videoId && videoId.length === 11) {
    return videoId;
  }

  // Метод 2: из ytInitialData (более надежный)
  try {
    const ytInitialData = window.ytInitialData;
    if (ytInitialData?.contents?.twoColumnWatchNextResults?.video?.videoDetails?.videoId) {
      return ytInitialData.contents.twoColumnWatchNextResults.video.videoDetails.videoId;
    }
  } catch (e) {
    console.warn('Could not extract video ID from ytInitialData');
  }

  return null;
}

/**
 * Получить субтитры для видео на странице YouTube
 */
async function fetchSubtitlesForCurrentVideo() {
  const videoId = getVideoIdFromPage();

  if (!videoId) {
    console.error('Could not determine video ID');
    return null;
  }

  console.log(`Fetching subtitles for video: ${videoId}`);

  try {
    const url = `https://web-production-bd8bb.up.railway.app/api/subtitles/${videoId}`;
    const response = await fetch(url);
    const data = await response.json();

    if (!data.success) {
      console.warn(`No subtitles available: ${data.error}`);
      return null;
    }

    console.log(`✅ Received ${data.count} subtitles in ${data.language}`);
    return data;

  } catch (error) {
    console.error('Error fetching subtitles:', error);
    return null;
  }
}

// Использование в popup или content script
document.getElementById('generate-description').addEventListener('click', async () => {
  const subtitlesData = await fetchSubtitlesForCurrentVideo();

  if (subtitlesData) {
    // Используйте subtitlesData.subtitles для генерации описания
    const description = generateDescriptionFromSubtitles(subtitlesData.subtitles);
    console.log(description);
  }
});
```

### TypeScript

```typescript
interface Subtitle {
  index: number;
  start: number;
  end: number;
  dur: number;
  text: string;
}

interface SubtitlesResponse {
  success: boolean;
  status: string;
  videoId: string;
  language: string | null;
  count: number;
  subtitles: Subtitle[];
  error?: string;
}

/**
 * Получить субтитры с type safety
 */
async function getYouTubeSubtitles(videoId: string): Promise<Subtitle[]> {
  const API_URL = 'https://web-production-bd8bb.up.railway.app';
  const url = `${API_URL}/api/subtitles/${videoId}`;

  const response = await fetch(url);
  const data: SubtitlesResponse = await response.json();

  if (!data.success) {
    throw new Error(data.error || 'Failed to fetch subtitles');
  }

  return data.subtitles;
}

// Использование
(async () => {
  const subtitles = await getYouTubeSubtitles('dQw4w9WgXcQ');

  subtitles.forEach(sub => {
    console.log(`[${sub.index}] ${sub.start.toFixed(2)}s - ${sub.end.toFixed(2)}s: ${sub.text}`);
  });
})();
```

### React

```jsx
import { useState, useEffect } from 'react';

function YouTubeSubtitlesComponent({ videoId }) {
  const [subtitles, setSubtitles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!videoId) return;

    setLoading(true);
    setError(null);

    fetch(`https://web-production-bd8bb.up.railway.app/api/subtitles/${videoId}`)
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          setSubtitles(data.subtitles);
        } else {
          setError(data.error);
        }
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [videoId]);

  if (loading) return <div>⏳ Loading subtitles...</div>;
  if (error) return <div>❌ Error: {error}</div>;
  if (subtitles.length === 0) return <div>No subtitles found</div>;

  return (
    <div className="subtitles">
      <h2>Subtitles ({subtitles.length})</h2>
      <div className="subtitle-list">
        {subtitles.map(sub => (
          <div key={sub.index} className="subtitle-item">
            <span className="time">[{sub.start.toFixed(2)}s]</span>
            <span className="text">{sub.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default YouTubeSubtitlesComponent;
```

### Python

```python
import requests

def get_youtube_subtitles(video_id: str) -> list:
    """
    Получить субтитры YouTube видео

    Args:
        video_id: YouTube video ID (11 символов)

    Returns:
        List of subtitle objects with keys: index, start, end, dur, text

    Raises:
        Exception: If video not found or no subtitles available
    """
    api_url = 'https://web-production-bd8bb.up.railway.app'
    url = f'{api_url}/api/subtitles/{video_id}'

    response = requests.get(url)
    data = response.json()

    if not data['success']:
        raise Exception(data.get('error', 'Unknown error'))

    return data['subtitles']

# Использование
if __name__ == '__main__':
    try:
        subtitles = get_youtube_subtitles('dQw4w9WgXcQ')
        print(f'Получено {len(subtitles)} субтитров')

        for sub in subtitles[:3]:
            print(f"[{sub['start']:.2f}s] {sub['text']}")

    except Exception as e:
        print(f'Error: {e}')
```

### cURL

```bash
# Базовый запрос
curl "https://web-production-bd8bb.up.railway.app/api/subtitles/dQw4w9WgXcQ"

# Pretty print JSON
curl "https://web-production-bd8bb.up.railway.app/api/subtitles/dQw4w9WgXcQ" | jq '.'

# Только количество и язык
curl "https://web-production-bd8bb.up.railway.app/api/subtitles/dQw4w9WgXcQ" | jq '{count: .count, language: .language}'

# Первые 5 субтитров
curl "https://web-production-bd8bb.up.railway.app/api/subtitles/dQw4w9WgXcQ" | jq '.subtitles[:5]'

# Проверить если есть субтитры
curl -s "https://web-production-bd8bb.up.railway.app/api/subtitles/dQw4w9WgXcQ" | jq 'if .success then "✅ Yes" else "❌ No" end'
```

---

## 🚨 Обработка ошибок

### Основные ошибки и как их обработать:

```javascript
async function robustGetSubtitles(videoId) {
  try {
    const response = await fetch(
      `https://web-production-bd8bb.up.railway.app/api/subtitles/${videoId}`
    );

    // Проверить HTTP статус
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();

    // Проверить success флаг
    if (!data.success) {
      // Различные типы ошибок
      if (data.error.includes('Invalid video ID')) {
        throw new Error('❌ Invalid video ID format');
      }
      if (data.error.includes('No subtitles')) {
        throw new Error('⚠️ This video has no subtitles');
      }
      if (data.error.includes('Video not found')) {
        throw new Error('❌ Video not found on YouTube');
      }

      // Неизвестная ошибка
      throw new Error(`API Error: ${data.error}`);
    }

    // Проверить что есть субтитры
    if (data.count === 0) {
      console.warn('⚠️ No subtitles in response');
      return [];
    }

    return data.subtitles;

  } catch (error) {
    if (error instanceof TypeError) {
      // Network error
      console.error('🌐 Network error - check internet connection');
    } else if (error instanceof SyntaxError) {
      // JSON parse error
      console.error('📄 Invalid JSON response from server');
    } else {
      console.error(error.message);
    }

    throw error;
  }
}
```

### HTTP Status Codes

| Код | Значение | Что делать |
|-----|----------|-----------|
| 200 | OK | Проверить `success` флаг в response body |
| 400 | Bad Request | Проверить format video ID (должен быть 11 символов) |
| 404 | Not Found | Видео не найдено на YouTube |
| 429 | Too Many Requests | Подождать перед следующим запросом |
| 500 | Server Error | Попробовать позже, сообщить в support |

---

## 🧪 Тестирование

### Тестовые видео

```javascript
// Все эти видео проверены и работают ✅

const TEST_VIDEOS = {
  // Видео с английскими субтитрами
  en: {
    id: 'dQw4w9WgXcQ',
    name: 'Rick Roll',
    count: 61
  },

  // Видео с русскими субтитрами
  ru: {
    id: 'fi7GI4hyIJc',
    name: 'Russian video',
    count: 569
  },

  // Видео с английскими субтитрами (длинное)
  en_long: {
    id: 'DvKZlIiiQGM',
    name: 'Long English video',
    count: 761
  }
};

// Тестовая функция
async function testSubtitles(video) {
  console.log(`Testing: ${video.name}`);

  try {
    const subtitles = await getYouTubeSubtitles(video.id);

    if (subtitles.length !== video.count) {
      console.warn(`⚠️ Expected ${video.count} but got ${subtitles.length}`);
    } else {
      console.log(`✅ Got ${subtitles.length} subtitles as expected`);
    }

    // Проверить структуру первого субтитра
    const first = subtitles[0];
    const hasRequiredFields = ['index', 'start', 'end', 'dur', 'text'].every(
      field => field in first
    );

    if (hasRequiredFields) {
      console.log('✅ Subtitle structure is correct');
    } else {
      console.error('❌ Subtitle structure is incorrect');
    }

  } catch (error) {
    console.error(`❌ ${error.message}`);
  }
}

// Запустить все тесты
for (const video of Object.values(TEST_VIDEOS)) {
  await testSubtitles(video);
  console.log('---');
}
```

### Проверка в консоли браузера

```javascript
// Скопируйте это в DevTools Console (F12) на странице YouTube видео

// 1. Получить video ID текущей страницы
const videoId = new URLSearchParams(window.location.search).get('v');
console.log('Video ID:', videoId);

// 2. Запросить субтитры
fetch(`https://web-production-bd8bb.up.railway.app/api/subtitles/${videoId}`)
  .then(r => r.json())
  .then(data => {
    console.log('✅ Response:', data);
    console.log(`📊 Count: ${data.count}, Language: ${data.language}`);
    if (data.subtitles.length > 0) {
      console.log('First subtitle:', data.subtitles[0]);
    }
  })
  .catch(e => console.error('❌ Error:', e));
```

---

## 🔧 Отладка

### Логирование для отладки

```javascript
async function debugGetSubtitles(videoId) {
  const API_URL = 'https://web-production-bd8bb.up.railway.app';
  const url = `${API_URL}/api/subtitles/${videoId}`;

  console.log(`[DEBUG] URL: ${url}`);
  console.log(`[DEBUG] Video ID: ${videoId}`);
  console.log(`[DEBUG] Fetching...`);

  const startTime = performance.now();

  try {
    const response = await fetch(url);
    const endTime = performance.now();

    console.log(`[DEBUG] Response time: ${(endTime - startTime).toFixed(2)}ms`);
    console.log(`[DEBUG] Status: ${response.status} ${response.statusText}`);
    console.log(`[DEBUG] Headers:`, {
      'content-type': response.headers.get('content-type'),
      'content-length': response.headers.get('content-length')
    });

    const data = await response.json();

    console.log(`[DEBUG] Full response:`, data);

    if (data.success) {
      console.log(`[DEBUG] ✅ Success!`);
      console.log(`[DEBUG] Count: ${data.count}`);
      console.log(`[DEBUG] Language: ${data.language}`);
      console.log(`[DEBUG] First subtitle:`, data.subtitles[0]);
    } else {
      console.log(`[DEBUG] ❌ API Error: ${data.error}`);
    }

    return data;

  } catch (error) {
    console.error(`[DEBUG] ❌ Network error:`, error);
    throw error;
  }
}

// Использование
debugGetSubtitles('dQw4w9WgXcQ');
```

### CORS Issues?

Если видите ошибку `CORS policy: No 'Access-Control-Allow-Origin' header`:

```javascript
// Проверить CORS headers
fetch('https://web-production-bd8bb.up.railway.app/api/health')
  .then(r => {
    console.log('CORS headers:');
    console.log('Access-Control-Allow-Origin:', r.headers.get('Access-Control-Allow-Origin'));
    console.log('Access-Control-Allow-Methods:', r.headers.get('Access-Control-Allow-Methods'));
    return r.json();
  })
  .then(d => console.log('✅ CORS is working:', d))
  .catch(e => console.error('❌ CORS error:', e));
```

---

## ❓ FAQ

### Q: Какой язык возвращает GET endpoint?
**A:** Всегда оригинальный язык видео. Параметр `lang` игнорируется.

### Q: Может ли видео иметь несколько языков субтитров?
**A:** Да, но GET endpoint возвращает только первый доступный (оригинальный).

### Q: Что если видео не на английском?
**A:** Идеально! GET endpoint возвращает оригинальный язык. Если видео на русском, получите русские субтитры.

### Q: Могу ли я перевести субтитры?
**A:** Нет, используйте POST endpoint если нужен перевод. GET endpoint только для оригинального языка.

### Q: Сколько времени занимает запрос?
**A:** Обычно 2-5 секунд в зависимости от:
- Размера видео (количество субтитров)
- Скорости интернета
- Очереди на сервере (при большом количестве одновременных запросов)

### Q: Какое максимальное количество субтитров?
**A:** Проверено на видео с 761 субтитром - работает идеально. Теоретически ограничения нет.

### Q: Как часто я могу делать запросы?
**A:** На сервере установлен rate limiter - максимум 2 запроса к YouTube в секунду. При большом количестве пользователей запросы автоматически становятся в очередь.

### Q: Что если YouTube заблокирует мой IP?
**A:** На сервере используются защиты от блокировки (rate limiting). Если проблемы - свяжитесь с support.

### Q: Есть ли API KEY?
**A:** Нет! API открытый и не требует аутентификации.

### Q: CORS проблемы?
**A:** API полностью поддерживает CORS для Chrome расширений. Проверьте консоль браузера для деталей.

### Q: Могу ли я использовать API на backend?
**A:** Да, полностью! Работает везде (Node.js, Python, Go, и т.д.).

---

## 📞 Support

### Что делать если что-то не работает?

1. **Проверьте video ID**
   - Должен быть ровно 11 символов
   - Пример: `dQw4w9WgXcQ` ✅
   - Неправильно: `youtube.com/watch?v=dQw4w9WgXcQ` ❌

2. **Проверьте что видео существует**
   - Откройте видео в браузере
   - Убедитесь что видео не удалено/приватное

3. **Проверьте что видео имеет субтитры**
   - На странице видео должна быть кнопка "CC" (Closed Captions)
   - Или параметр "captions" в информации о видео

4. **Проверьте сетевое соединение**
   - Откройте DevTools (F12)
   - Перейдите на Network tab
   - Сделайте запрос
   - Должен быть status 200 OK

5. **Свяжитесь с support**
   - Напишите в Issues на GitHub с:
     - Video ID который не работает
     - Error message из консоли
     - Шаги для воспроизведения проблемы

### GitHub Issues
```
https://github.com/AlexRunch/youtube-transcript-api-nov25/issues
```

Укажите:
- ❌ Что не работает
- 📺 Video ID для теста
- 💬 Error message
- 🔧 Ваша среда (Chrome, Firefox, Node.js, etc.)

---

## 📊 Server Status

Статус двух доступных серверов:

### Server 1 (Original)
```
URL: https://web-production-bd8bb.up.railway.app
Status: ✅ Active
Last update: 2025-11-17
```

### Server 2 (Backup)
```
URL: https://web-production-19e72.up.railway.app
Status: ✅ Active
Last update: 2025-11-17
```

Можно использовать любой. Они синхронизированы.

---

## 📝 Changelog

### v2.0 (2025-11-17)
- ✨ Исправлен GET endpoint
- 🛡️ Добавлен YouTube rate limiting
- 📚 Расширена документация
- ✅ Протестирована интеграция на 3 видео

### v1.0 (2025-11-14)
- 🚀 Изначальный релиз GET endpoint

---

## 🎓 Best Practices

### ✅ Делайте:
- Обрабатывайте ошибки gracefully
- Показывайте пользователю понятные сообщения об ошибках
- Кэшируйте результаты если делаете много запросов
- Логируйте ошибки для отладки
- Используйте видео ID 11 символов

### ❌ Не делайте:
- Не отправляйте одновременно 100+ запросов
- Не используйте полный YouTube URL вместо video ID
- Не игнорируйте `success: false` ответы
- Не забывайте обработку ошибок
- Не передавайте credentials в запросе

---

## 🚀 Готово к использованию!

```javascript
// Скопируйте и используйте:
const API_URL = 'https://web-production-bd8bb.up.railway.app/api/subtitles';

async function getSubtitles(videoId) {
  const response = await fetch(`${API_URL}/${videoId}`);
  const data = await response.json();

  if (!data.success) throw new Error(data.error);
  return data.subtitles;
}
```

**Happy coding! 🎉**

---

*Документация актуальна на: 17 ноября 2025*
*Последнее обновление: 2025-11-17*
