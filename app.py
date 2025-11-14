"""
YouTube Subtitles API Backend
===============================
Простой Flask сервер для получения субтитров YouTube через youtube-transcript-api

Использование:
  POST /api/subtitles
  {
    "videoId": "E19_kwN0f38",
    "language": "en",
    "translateTo": null  // или "ru" для перевода
  }

Разворачивается на Railway
"""

import os
import json
import logging
import traceback
from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

# Попытка импортировать proxy config
try:
    from youtube_transcript_api.proxies import WebshareProxyConfig
    PROXY_CONFIG_AVAILABLE = True
    PROXY_TYPE = "webshare"
except ImportError:
    try:
        from youtube_transcript_api.proxies import GenericProxyConfig
        PROXY_CONFIG_AVAILABLE = True
        PROXY_TYPE = "generic"
    except ImportError:
        PROXY_CONFIG_AVAILABLE = False
        PROXY_TYPE = None

# ============================================================================
# ЛОГИРОВАНИЕ
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# ИНИЦИАЛИЗАЦИЯ FLASK
# ============================================================================
app = Flask(__name__)

# CORS поддержка для Chrome расширения и YouTube
try:
    from flask_cors import CORS

    # Разрешить запросы с:
    # 1. Chrome расширений (любых)
    # 2. YouTube.com и всех поддоменов
    # 3. www.youtube.com
    cors_config = {
        "origins": [
            "chrome-extension://*",           # Все Chrome расширения
            "https://www.youtube.com",        # YouTube (www версия)
            "https://youtube.com",            # YouTube (без www)
            "https://*.youtube.com"           # Все поддомены YouTube
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }

    CORS(app, resources={"/api/*": cors_config})
    logger.info("✅ CORS включен для Chrome расширений и YouTube")
except ImportError:
    logger.error("❌ flask-cors не установлен! CORS отключен. Расширение работать не будет!")

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================
PORT = int(os.getenv('PORT', 5000))
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# Конфигурация прокси для Webshare (решает проблему блокировки Railway IP)
# Временно отключаем прокси для тестирования
WEBSHARE_USERNAME = None  # os.getenv('WEBSHARE_PROXY_USERNAME', None)
WEBSHARE_PASSWORD = None  # os.getenv('WEBSHARE_PROXY_PASSWORD', None)

# Инициализируем YouTube API с прокси если доступны credentials
youtube_api = None
if WEBSHARE_USERNAME and WEBSHARE_PASSWORD:
    try:
        if PROXY_CONFIG_AVAILABLE and PROXY_TYPE == "webshare":
            # Используем WebshareProxyConfig если доступна
            proxy_config = WebshareProxyConfig(
                proxy_username=WEBSHARE_USERNAME,
                proxy_password=WEBSHARE_PASSWORD
            )
            youtube_api = YouTubeTranscriptApi(proxy_config=proxy_config)
            logger.info("✅ YouTube API инициализирован с Webshare прокси (WebshareProxyConfig)")
        elif PROXY_CONFIG_AVAILABLE and PROXY_TYPE == "generic":
            # Используем GenericProxyConfig для старых версий или других провайдеров
            # Формат URL: http://username:password@host:port
            # Webshare может требовать порт 3128 или 80
            proxy_url = f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@proxy.webshare.io:3128"
            proxy_config = GenericProxyConfig(http_proxy=proxy_url, https_proxy=proxy_url)
            youtube_api = YouTubeTranscriptApi(proxy_config=proxy_config)
            logger.info("✅ YouTube API инициализирован с Webshare прокси (GenericProxyConfig на порту 3128)")
        else:
            # Если прокси конфиг не доступен, создаем обычный API
            # Прокси может не быть поддержана в версии 0.6.1-0.6.2
            logger.warning(f"⚠️ Proxy config не доступна (тип: {PROXY_TYPE}), используем обычный API")
            youtube_api = YouTubeTranscriptApi()
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации прокси: {str(e)}, используем обычный API")
        logger.error(f"📋 Stack trace: {traceback.format_exc()}")
        youtube_api = YouTubeTranscriptApi()
else:
    youtube_api = YouTubeTranscriptApi()
    if not WEBSHARE_USERNAME or not WEBSHARE_PASSWORD:
        logger.warning("⚠️ Переменные окружения WEBSHARE_PROXY_USERNAME/PASSWORD не установлены")

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def format_subtitles(transcript_list):
    """
    Преобразует format youtube-transcript-api в наш формат

    Входящий формат (новая версия - объекты):
    [
        FetchedTranscriptSnippet(text="Hello", start=0.5, duration=1.5),
        ...
    ]

    Входящий формат (старая версия - словари):
    [
        {"text": "Hello", "start": 0.5, "duration": 1.5},
        ...
    ]

    Выходящий формат:
    [
        {"time": 0.5, "duration": 1.5, "text": "Hello"},
        ...
    ]
    """
    result = []
    for item in transcript_list:
        # Обработка объектов FetchedTranscriptSnippet (новая версия)
        if hasattr(item, 'text'):
            # Это объект с атрибутами
            result.append({
                "time": float(getattr(item, 'start', 0)),
                "duration": float(getattr(item, 'duration', 0)),
                "text": getattr(item, 'text', '')
            })
        else:
            # Это словарь (старая версия)
            result.append({
                "time": float(item.get("start", 0)),
                "duration": float(item.get("duration", 0)),
                "text": item.get("text", "")
            })
    return result


def format_subtitles_for_extension(transcript_list):
    """
    Преобразует субтитры в формат для второго расширения (YouTube Description Generator + Title & Chapters).

    Входящий формат (youtube-transcript-api):
    [
        {"text": "Hello", "start": 0.5, "duration": 1.5},
        ...
    ]

    Выходящий формат:
    [
        {"index": 0, "start": 0.5, "end": 2.0, "dur": 1.5, "text": "Hello"},
        ...
    ]
    """
    result = []
    for index, item in enumerate(transcript_list):
        # Получаем значения start и duration
        if hasattr(item, 'text'):
            # Это объект FetchedTranscriptSnippet (новая версия)
            start = float(getattr(item, 'start', 0))
            duration = float(getattr(item, 'duration', 0))
            text = getattr(item, 'text', '')
        else:
            # Это словарь (старая версия)
            start = float(item.get("start", 0))
            duration = float(item.get("duration", 0))
            text = item.get("text", "")

        # Вычисляем end время
        end = start + duration

        result.append({
            "index": index,
            "start": start,
            "end": end,
            "dur": duration,
            "text": text
        })

    return result


def get_available_languages(video_id):
    """Получить список доступных языков для видео"""
    try:
        # Новый API использует .list() вместо .list_transcripts()
        try:
            transcript_list = youtube_api.list(video_id)
        except AttributeError:
            # Fallback для старых версий
            transcript_list = youtube_api.list_transcripts(video_id)

        # Доступные языки (с автоматическими субтитрами и без)
        languages = []

        # Вручную созданные субтитры (старая версия API)
        if hasattr(transcript_list, 'manually_created_transcripts') and transcript_list.manually_created_transcripts:
            try:
                for transcript in transcript_list.manually_created_transcripts:
                    languages.append({
                        "code": transcript.language_code,
                        "name": transcript.language,
                        "isAuto": False
                    })
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при обработке вручную созданных субтитров: {str(e)}")

        # Автоматически сгенерированные субтитры (старая версия API)
        if hasattr(transcript_list, 'automatically_generated_transcripts') and transcript_list.automatically_generated_transcripts:
            try:
                for transcript in transcript_list.automatically_generated_transcripts:
                    languages.append({
                        "code": transcript.language_code,
                        "name": transcript.language,
                        "isAuto": True
                    })
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при обработке автоматических субтитров: {str(e)}")

        logger.info(f"✅ Найдено {len(languages)} языков для видео {video_id}")
        return languages
    except Exception as e:
        logger.error(f"❌ Ошибка при получении языков для {video_id}: {str(e)}")
        logger.error(f"📋 Stack trace: {traceback.format_exc()}")
        return []


# ============================================================================
# API ЭНДПОИНТЫ
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Проверка здоровья сервера"""
    return jsonify({
        "ok": True,
        "service": "YouTube Subtitles API",
        "timestamp": __import__('datetime').datetime.utcnow().isoformat()
    }), 200


@app.route('/api/subtitles', methods=['POST'])
def get_subtitles():
    """
    Основной эндпоинт для получения субтитров

    Request:
    {
        "videoId": "E19_kwN0f38",
        "language": "en",
        "translateTo": null  // или "ru"
    }

    Response:
    {
        "success": true,
        "videoId": "E19_kwN0f38",
        "language": "en",
        "subtitles": [
            {"time": 0.5, "duration": 1.5, "text": "Hello"},
            ...
        ],
        "availableLanguages": [...]
    }
    """
    try:
        data = request.get_json() or {}
        video_id = data.get('videoId', '').strip()
        language = data.get('language', 'en').strip()
        translate_to = data.get('translateTo', None)

        # ===== ВАЛИДАЦИЯ =====
        if not video_id:
            logger.warning("❌ Пустой videoId")
            return jsonify({
                "success": False,
                "error": "videoId is required"
            }), 400

        if not isinstance(video_id, str) or len(video_id) != 11:
            logger.warning(f"❌ Неверный формат videoId: {video_id}")
            return jsonify({
                "success": False,
                "error": "Invalid videoId format (must be 11 characters)"
            }), 400

        logger.info(f"📥 Запрос: видео {video_id}, язык {language}, перевод {translate_to}")

        # ===== ПОЛУЧЕНИЕ СУБТИТРОВ =====
        try:
            # Список доступных транскриптов для видео
            logger.info(f"📡 Запрашиваем список транскриптов для видео {video_id}...")

            # Новый API использует .list() вместо .list_transcripts()
            try:
                transcript_list = youtube_api.list(video_id)
            except AttributeError:
                # Fallback для старых версий
                transcript_list = youtube_api.list_transcripts(video_id)

            logger.info(f"✅ Получен список транскриптов для {video_id}")

            # Пытаемся получить субтитры на запрашиваемом языке
            transcript = None

            # Пробуем найти субтитры на запрашиваемом языке
            try:
                transcript = transcript_list.find_transcript([language])
                logger.info(f"✅ Найдены субтитры на {language}")
            except NoTranscriptFound:
                logger.warning(f"⚠️ Субтитры на {language} не найдены")
                # Запрошенный язык недоступен - возвращаем ошибку (без fallback)
                return jsonify({
                    "success": False,
                    "error": f"Subtitles not available for language: {language}"
                }), 404

            # Получаем субтитры (с переводом если нужен)
            if translate_to and translate_to != language:
                logger.info(f"🌐 Переводим субтитры на {translate_to}")
                try:
                    translated = transcript.translate(translate_to)
                    subtitle_data = translated.fetch()
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка перевода на {translate_to}, используем оригинал: {str(e)}")
                    subtitle_data = transcript.fetch()
            else:
                subtitle_data = transcript.fetch()

            # Форматируем субтитры
            formatted_subtitles = format_subtitles(subtitle_data)

            logger.info(f"✅ Успешно получены {len(formatted_subtitles)} субтитров для {video_id}")

            # Получаем реальный язык который был использован
            actual_language = transcript.language_code if hasattr(transcript, 'language_code') else language

            return jsonify({
                "success": True,
                "videoId": video_id,
                "requestedLanguage": language,  # Язык которого просил клиент
                "language": actual_language,     # Язык который был найден
                "translatedTo": translate_to,
                "subtitles": formatted_subtitles,
                "count": len(formatted_subtitles)
            }), 200

        except TranscriptsDisabled:
            logger.error(f"❌ Субтитры отключены для видео {video_id}")
            return jsonify({
                "success": False,
                "error": "Transcripts are disabled for this video"
            }), 403

        except VideoUnavailable:
            logger.error(f"❌ Видео недоступно: {video_id}")
            return jsonify({
                "success": False,
                "error": "Video is unavailable"
            }), 404

        except Exception as e:
            logger.error(f"❌ Ошибка получения субтитров: {str(e)}")
            return jsonify({
                "success": False,
                "error": f"Failed to fetch transcripts: {str(e)}"
            }), 500

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в /api/subtitles: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500


@app.route('/api/languages/<video_id>', methods=['GET'])
def get_languages(video_id):
    """Получить список доступных языков для видео"""
    try:
        video_id = video_id.strip()

        if not video_id or len(video_id) != 11:
            return jsonify({
                "success": False,
                "error": "Invalid videoId"
            }), 400

        logger.info(f"📥 Запрос языков для видео {video_id}")

        languages = get_available_languages(video_id)

        logger.info(f"✅ Найдено {len(languages)} языков")

        return jsonify({
            "success": True,
            "videoId": video_id,
            "languages": languages
        }), 200

    except Exception as e:
        logger.error(f"❌ Ошибка получения языков: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/subtitles/<video_id>', methods=['GET'])
def get_subtitles_v2(video_id):
    """
    GET эндпоинт для получения субтитров (для второго расширения).
    Возвращает субтитры в формате: {index, start, end, dur, text}

    Query Parameters:
    - lang: язык субтитров (обязательно)
    - format: формат ответа (json по умолчанию)

    Пример:
    GET /api/subtitles/dQw4w9WgXcQ?lang=en

    Response:
    {
        "success": true,
        "status": "completed",
        "videoId": "dQw4w9WgXcQ",
        "language": "en",
        "count": 42,
        "subtitles": [
            {"index": 0, "start": 0.5, "end": 3.2, "dur": 2.7, "text": "Hello"},
            ...
        ]
    }
    """
    try:
        # Валидируем video_id
        video_id = video_id.strip()
        if not video_id or len(video_id) != 11:
            return jsonify({
                "success": False,
                "status": "error",
                "error": "Invalid video ID format. Must be 11 characters.",
                "videoId": video_id
            }), 400

        # Получаем параметры запроса
        language = request.args.get('lang', 'en').strip()
        response_format = request.args.get('format', 'json').strip()

        if not language:
            return jsonify({
                "success": False,
                "status": "error",
                "error": "Missing required parameter: lang",
                "videoId": video_id
            }), 400

        logger.info(f"📥 GET запрос: видео {video_id}, язык {language}")

        # ===== ПОЛУЧЕНИЕ СУБТИТРОВ =====
        try:
            # Получаем список доступных транскриптов
            try:
                transcript_list = youtube_api.list(video_id)
            except AttributeError:
                transcript_list = youtube_api.list_transcripts(video_id)

            logger.info(f"✅ Получен список транскриптов для {video_id}")

            # Пытаемся получить субтитры на запрашиваемом языке
            transcript = None

            try:
                transcript = transcript_list.find_transcript([language])
                logger.info(f"✅ Найдены субтитры на {language}")
            except NoTranscriptFound:
                logger.warning(f"⚠️ Субтитры на {language} не найдены")
                # Запрошенный язык недоступен - возвращаем ошибку (без fallback)
                return jsonify({
                    "success": False,
                    "status": "error",
                    "error": f"No subtitles found for language: {language}",
                    "videoId": video_id,
                    "language": language,
                    "count": 0,
                    "subtitles": []
                }), 200

            # Получаем субтитры
            subtitle_data = transcript.fetch()

            # Форматируем субтитры в требуемый формат
            formatted_subtitles = format_subtitles_for_extension(subtitle_data)

            logger.info(f"✅ Успешно получены {len(formatted_subtitles)} субтитров для {video_id}")

            actual_language = transcript.language_code if hasattr(transcript, 'language_code') else language

            return jsonify({
                "success": True,
                "status": "completed",
                "videoId": video_id,
                "language": actual_language,
                "count": len(formatted_subtitles),
                "subtitles": formatted_subtitles
            }), 200

        except TranscriptsDisabled:
            logger.error(f"❌ Субтитры отключены для видео {video_id}")
            return jsonify({
                "success": False,
                "status": "error",
                "error": "Transcripts are disabled for this video",
                "videoId": video_id,
                "language": language,
                "count": 0,
                "subtitles": []
            }), 200

        except VideoUnavailable:
            logger.error(f"❌ Видео недоступно: {video_id}")
            return jsonify({
                "success": False,
                "status": "error",
                "error": "Video not found on YouTube",
                "videoId": video_id
            }), 404

        except Exception as e:
            logger.error(f"❌ Ошибка получения субтитров: {str(e)}")
            return jsonify({
                "success": False,
                "status": "error",
                "error": f"Failed to fetch subtitles: {str(e)}",
                "videoId": video_id,
                "language": language,
                "count": 0,
                "subtitles": []
            }), 200

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в /api/subtitles/<videoId>: {str(e)}")
        return jsonify({
            "success": False,
            "status": "error",
            "error": "Internal server error"
        }), 500


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Endpoint not found"
    }), 404


@app.errorhandler(500)
def server_error(error):
    logger.error(f"❌ Server error: {str(error)}")
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500


# ============================================================================
# ЗАПУСК СЕРВЕРА
# ============================================================================

if __name__ == '__main__':
    logger.info(f"🚀 Запуск YouTube Subtitles API сервера на порту {PORT}")
    logger.info(f"📍 Здоровье: http://localhost:{PORT}/api/health")
    logger.info(f"📍 API: POST http://localhost:{PORT}/api/subtitles")

    # Railway требует слушать на 0.0.0.0
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=DEBUG,
        threaded=True
    )
