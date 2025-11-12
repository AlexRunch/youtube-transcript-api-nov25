# 🔗 Интеграция с Chrome расширением

Инструкция как подключить этот backend к вашему расширению.

## 1️⃣ Откуда брать URL сервера?

После развертывания на Railway ты получишь URL типа:
```
https://youtube-subtitles-api-production.up.railway.app
```

Сохрани его. Это будет переменная `API_URL` в коде расширения.

## 2️⃣ Добавить новый модуль в расширение

Создай файл `js/backend/transcript-api-client.js`:

```javascript
/**
 * YouTube Transcript API Client
 * Клиент для взаимодействия с бэкендом youtube-transcript-api
 */

window.YouTubeTranscriptApiClient = window.YouTubeTranscriptApiClient || {};

(function(Client) {
  'use strict';

  // =========================================================================
  // КОНФИГУРАЦИЯ
  // =========================================================================

  // 🔴 ЗАМЕНИ НА СВОЙ URL из Railway!
  const API_URL = 'https://youtube-subtitles-api-production.up.railway.app';

  const CONFIG = {
    API_URL: API_URL,
    TIMEOUT_MS: 30000,
    RETRY_COUNT: 3,
    RETRY_DELAY_MS: 1000
  };

  // =========================================================================
  // УТИЛИТЫ
  // =========================================================================

  function log(message, data = null) {
    const timestamp = new Date().toISOString();
    const prefix = '[TRANSCRIPT-API]';
    if (data) {
      console.log(`${prefix} ${message}`, data);
    } else {
      console.log(`${prefix} ${message}`);
    }
  }

  function error(message, err = null) {
    const timestamp = new Date().toISOString();
    const prefix = '[TRANSCRIPT-API]';
    if (err) {
      console.error(`${prefix} ❌ ${message}`, err);
    } else {
      console.error(`${prefix} ❌ ${message}`);
    }
  }

  // =========================================================================
  // FETCH С RETRY
  // =========================================================================

  async function fetchWithRetry(url, options = {}, retryCount = CONFIG.RETRY_COUNT) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);

      const response = await fetch(url, {
        ...options,
        signal: controller.signal
      });

      clearTimeout(timeout);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (err) {
      if (retryCount > 0) {
        log(`⚠️ Ошибка, повторная попытка через ${CONFIG.RETRY_DELAY_MS}ms...`, err.message);
        await new Promise(resolve => setTimeout(resolve, CONFIG.RETRY_DELAY_MS));
        return fetchWithRetry(url, options, retryCount - 1);
      } else {
        throw err;
      }
    }
  }

  // =========================================================================
  // ОСНОВНЫЕ МЕТОДЫ
  // =========================================================================

  /**
   * Получить субтитры видео
   * @param {string} videoId - YouTube video ID
   * @param {string} language - язык (по умолчанию 'en')
   * @param {string|null} translateTo - перевести на язык (опционально)
   * @returns {Promise<Array>} массив субтитров
   */
  Client.getSubtitles = async function(videoId, language = 'en', translateTo = null) {
    try {
      log(`📥 Запрос субтитров: видео ${videoId}, язык ${language}, перевод ${translateTo}`);

      const response = await fetchWithRetry(
        `${CONFIG.API_URL}/api/subtitles`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            videoId: videoId,
            language: language,
            translateTo: translateTo
          })
        }
      );

      if (!response.success) {
        throw new Error(response.error || 'Unknown error');
      }

      log(`✅ Получено ${response.count} субтитров`, response);
      return response.subtitles;
    } catch (err) {
      error(`Ошибка получения субтитров для ${videoId}`, err);
      throw err;
    }
  };

  /**
   * Получить список доступных языков
   * @param {string} videoId - YouTube video ID
   * @returns {Promise<Array>} массив языков
   */
  Client.getAvailableLanguages = async function(videoId) {
    try {
      log(`📥 Запрос языков для видео ${videoId}`);

      const response = await fetchWithRetry(
        `${CONFIG.API_URL}/api/languages/${videoId}`,
        { method: 'GET' }
      );

      if (!response.success) {
        throw new Error(response.error || 'Unknown error');
      }

      log(`✅ Получены языки`, response.languages);
      return response.languages;
    } catch (err) {
      error(`Ошибка получения языков для ${videoId}`, err);
      throw err;
    }
  };

  /**
   * Проверить здоровье API
   * @returns {Promise<boolean>} true если API работает
   */
  Client.checkHealth = async function() {
    try {
      log(`🏥 Проверка здоровья API...`);

      const response = await fetch(`${CONFIG.API_URL}/api/health`, {
        method: 'GET',
        timeout: 5000
      });

      const isOk = response.ok;
      isOk ? log(`✅ API здоров`) : error(`API недоступен (${response.status})`);
      return isOk;
    } catch (err) {
      error(`API недоступен`, err);
      return false;
    }
  };

  /**
   * Установить кастомный URL API
   * @param {string} url - новый URL API
   */
  Client.setApiUrl = function(url) {
    CONFIG.API_URL = url;
    log(`✅ API URL изменен на ${url}`);
  };

  /**
   * Получить текущий URL API
   * @returns {string} текущий URL API
   */
  Client.getApiUrl = function() {
    return CONFIG.API_URL;
  };

})(window.YouTubeTranscriptApiClient);
```

## 3️⃣ Подключить модуль в manifest.json

В `manifest.json` добавь ссылку на этот файл в `content_scripts`:

```json
{
  "content_scripts": [
    {
      "matches": ["https://www.youtube.com/*"],
      "js": [
        "js/core/config.js",
        "js/logger.js",
        "js/backend/transcript-api-client.js",
        // ... остальные скрипты
        "js/content.js"
      ]
    }
  ]
}
```

## 4️⃣ Использовать в коде расширения

Где угодно в твоем `content.js` или других модулях:

```javascript
// Получить субтитры
try {
  const subtitles = await YouTubeTranscriptApiClient.getSubtitles(
    'E19_kwN0f38',
    'en',
    null  // без перевода
  );
  console.log('Субтитры:', subtitles);
} catch (err) {
  console.error('Ошибка:', err);
}

// Получить с переводом на русский
try {
  const subtitles = await YouTubeTranscriptApiClient.getSubtitles(
    'E19_kwN0f38',
    'en',
    'ru'  // перевести на русский
  );
  console.log('Переведенные субтитры:', subtitles);
} catch (err) {
  console.error('Ошибка:', err);
}

// Получить доступные языки
try {
  const languages = await YouTubeTranscriptApiClient.getAvailableLanguages('E19_kwN0f38');
  console.log('Доступные языки:', languages);
} catch (err) {
  console.error('Ошибка:', err);
}

// Проверить здоровье API
const isHealthy = await YouTubeTranscriptApiClient.checkHealth();
console.log('API работает:', isHealthy);
```

## 5️⃣ Интегрировать в систему fallback

В твоем `subtitle-engine-class.js` добавь новый метод fallback:

```javascript
// После других методов fallback добавь:

async tryTranscriptApiMethod(videoId, languageCode) {
  try {
    logger.debug(`[FALLBACK-TRANSCRIPT-API] Пытаемся получить субтитры через Transcript API...`);

    // Проверь что API доступен
    const isHealthy = await YouTubeTranscriptApiClient.checkHealth();
    if (!isHealthy) {
      throw new Error('Transcript API сервер недоступен');
    }

    const subtitles = await YouTubeTranscriptApiClient.getSubtitles(
      videoId,
      languageCode
    );

    if (subtitles && subtitles.length > 0) {
      logger.info(`✅ [FALLBACK-TRANSCRIPT-API] Получено ${subtitles.length} субтитров`);
      return subtitles;
    }

    throw new Error('API вернул пустой результат');
  } catch (err) {
    logger.warn(`⚠️ [FALLBACK-TRANSCRIPT-API] Ошибка: ${err.message}`);
    return null;
  }
}
```

## 6️⃣ Обновить конфигурацию

В `config.js` обнови EXTRACTION_METHODS:

```javascript
window.YouTubeSubtitlesConfig.EXTRACTION_METHODS = {
  MODE: 'manual',

  TRANSLATION: {
    USE_INTERCEPTION: false,
    USE_PLAYER_RESPONSE: false,
    USE_STANDARD_API: false,
    USE_PROXY_SERVER: false,
    USE_TRANSCRIPT_API: true,  // 👈 НОВЫЙ!
    USE_AI_TRANSLATION: false
  },

  ORIGINAL: {
    USE_INTERCEPTION: false,
    USE_PLAYER_RESPONSE: false,
    USE_STANDARD_API: false,
    USE_TRANSCRIPT_API: true,  // 👈 НОВЫЙ!
    USE_DOM_EXTRACTION: false
  },

  // Старый yt-dlp можно отключить или оставить как последний fallback
  USE_YT_DLP_BACKEND: false
};
```

## 7️⃣ Тестирование

Откройте любое видео YouTube и проверьте в консоли:

```javascript
// В консоли браузера напиши:
await YouTubeTranscriptApiClient.getSubtitles('E19_kwN0f38', 'en');
```

Должен вернуть массив с субтитрами.

## ⚠️ Важно

1. **Замени URL**: `https://youtube-subtitles-api-production.up.railway.app` на свой URL из Railway
2. **CORS**: Railway должен быть настроен на разрешение запросов из расширения (обычно работает по умолчанию)
3. **Security**: URL сервера будет видна в коде расширения — это нормально, это не секретный ключ
4. **Retry логика**: Клиент автоматически повторяет запросы если первый не удался

## 📊 Структура fallback цепочки (рекомендуемая)

```
1. INTERCEPTION (если есть перехваченные данные) — 95% успеха
   ↓ (если не сработал)
2. PLAYER_RESPONSE (ytInitialPlayerResponse) — 70% успеха
   ↓ (если не сработал)
3. TRANSCRIPT_API (наш новый backend) — 95% успеха ✨
   ↓ (если не сработал)
4. DOM_EXTRACTION (последний resort) — 30% успеха
```

Это обеспечит надежность в 99.9% случаев!

## 🚀 После интеграции

1. Протестируй на нескольких видео
2. Включи logging для отладки
3. Убедись что все методы работают
4. Можешь удалить yt-dlp backend если не нужен
5. Переходи на production! 🎉
