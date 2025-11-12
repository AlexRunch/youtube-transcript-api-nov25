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
from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

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

# CORS поддержка (если нужна)
try:
    from flask_cors import CORS
    CORS(app, origins=["chrome-extension://*", "https://*.youtube.com"])
except ImportError:
    logger.warning("flask-cors не установлен, CORS отключен")

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================
PORT = int(os.getenv('PORT', 5000))
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def format_subtitles(transcript_list):
    """
    Преобразует formаt youtube-transcript-api в наш формат

    Входящий формат:
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
    return [
        {
            "time": float(item.get("start", 0)),
            "duration": float(item.get("duration", 0)),
            "text": item.get("text", "")
        }
        for item in transcript_list
    ]


def get_available_languages(video_id):
    """Получить список доступных языков для видео"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Доступные языки (с автоматическими субтитрами и без)
        languages = []

        # Вручную созданные субтитры
        for transcript in transcript_list.manually_created_transcripts:
            languages.append({
                "code": transcript.language_code,
                "name": transcript.language,
                "isAuto": False
            })

        # Автоматически сгенерированные субтитры
        for transcript in transcript_list.automatically_generated_transcripts:
            languages.append({
                "code": transcript.language_code,
                "name": transcript.language,
                "isAuto": True
            })

        return languages
    except Exception as e:
        logger.error(f"❌ Ошибка при получении языков для {video_id}: {str(e)}")
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
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # Пытаемся получить субтитры на запрашиваемом языке
            transcript = None

            # Сначала пробуем вручную созданные субтитры
            try:
                transcript = transcript_list.find_transcript([language])
                logger.info(f"✅ Найдены вручную созданные субтитры: {language}")
            except NoTranscriptFound:
                # Если не найдены, пробуем автоматические
                try:
                    transcript = transcript_list.find_transcript([language])
                    logger.info(f"✅ Найдены автоматические субтитры: {language}")
                except NoTranscriptFound:
                    logger.warning(f"⚠️ Субтитры на {language} не найдены, используем первый доступный")
                    # Берем первый доступный язык
                    if transcript_list.manually_created_transcripts:
                        transcript = transcript_list.manually_created_transcripts[0]
                    elif transcript_list.automatically_generated_transcripts:
                        transcript = transcript_list.automatically_generated_transcripts[0]
                    else:
                        return jsonify({
                            "success": False,
                            "error": "No transcripts available for this video"
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

            return jsonify({
                "success": True,
                "videoId": video_id,
                "language": language,
                "translatedTo": translate_to,
                "subtitles": formatted_subtitles,
                "count": len(formatted_subtitles),
                "availableLanguages": get_available_languages(video_id)
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
