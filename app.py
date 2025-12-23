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
import time
import threading
from queue import Queue
from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
from youtube_transcript_api.proxies import WebshareProxyConfig
import requests
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Supabase для персистентного хранилища статистики
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("⚠️ Supabase не установлен - используется локальный JSON файл")


# ============================================================================
# ЛОГИРОВАНИЕ
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# ERROR TRACKING И BLOCKAGE DETECTION
# ============================================================================

class ErrorTracker:
    """
    Отслеживает ошибки от YouTube API и обнаруживает признаки блокировки
    """
    def __init__(self):
        self.errors = []  # История последних 100 ошибок
        self.http_429_count = 0  # Количество "Too Many Requests"
        self.http_403_count = 0  # Количество "Forbidden"
        self.timeout_count = 0  # Количество timeouts
        self.consecutive_failures = 0  # Ошибки подряд
        self.last_error_time = None
        self.lock = threading.Lock()
        self.error_window_minutes = 60  # Окно для подсчета ошибок

    def record_error(self, error_type, status_code=None, response_text="", video_id=""):
        """Записать ошибку"""
        with self.lock:
            error_info = {
                'timestamp': time.time(),
                'error_type': error_type,
                'status_code': status_code,
                'response_text': response_text[:100],  # Первые 100 символов
                'video_id': video_id
            }

            self.errors.append(error_info)

            # Хранить только последние 100 ошибок
            if len(self.errors) > 100:
                self.errors.pop(0)

            self.last_error_time = time.time()
            self.consecutive_failures += 1

            # Подсчет типов ошибок
            if status_code == 429:
                self.http_429_count += 1
            elif status_code == 403:
                self.http_403_count += 1
            elif 'timeout' in error_type.lower():
                self.timeout_count += 1

    def reset_consecutive_failures(self):
        """Сброс счетчика ошибок подряд при успехе"""
        with self.lock:
            self.consecutive_failures = 0

    def get_error_rate(self):
        """Получить процент ошибок за последний час"""
        with self.lock:
            now = time.time()
            recent_errors = [e for e in self.errors
                           if now - e['timestamp'] < self.error_window_minutes * 60]
            return len(recent_errors)

    def has_429(self):
        """Была ли обнаружена HTTP 429?"""
        with self.lock:
            return self.http_429_count > 0

    def has_403(self):
        """Была ли обнаружена HTTP 403?"""
        with self.lock:
            return self.http_403_count > 0

# Глобальный tracker ошибок
error_tracker = ErrorTracker()

# ============================================================================
# RATE LIMITING И КОНТРОЛЬ ОДНОВРЕМЕННЫХ ЗАПРОСОВ К YOUTUBE
# ============================================================================
class YouTubeRateLimiter:
    """
    Контролирует частоту запросов к YouTube чтобы избежать блокировки.

    Стратегия:
    - С rotating residential proxy: БЕЗ задержки (min_interval=0.0)
      Каждый запрос идет с разного IP, блокировка невозможна
    - Без proxy: 0.5 секунды между запросами (для защиты от блокировки)
    - При большом количестве пользователей запросы будут ставиться в очередь
    """
    def __init__(self, min_interval=0.5):
        self.min_interval = min_interval  # минимум секунд между YouTube запросами
        self.last_request_time = 0
        self.lock = threading.Lock()

    def wait_if_needed(self):
        """Подождать если нужно перед следующим YouTube запросом"""
        with self.lock:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                logger.info(f"⏱️ Rate limiter: ожидание {sleep_time:.2f}сек перед запросом к YouTube")
                time.sleep(sleep_time)
            self.last_request_time = time.time()

# Глобальный rate limiter для YouTube запросов (будет инициализирован после определения proxy конфига)
youtube_rate_limiter = None

# ============================================================================
# REQUEST MONITORING (для отслеживания YouTube API запросов)
# ============================================================================
class RequestMonitor:
    """
    Мониторит количество запросов к YouTube и отслеживает ошибки.
    Сохраняет статистику в Supabase (основное) и JSON файл (fallback).
    """
    def __init__(self, stats_file=None, supabase_client=None):
        self.requests_per_minute = 0
        self.requests_per_hour = 0
        self.last_reset_minute = time.time()
        self.last_reset_hour = time.time()
        self.lock = threading.Lock()
        self.request_log = []  # Log последних 100 запросов

        # Supabase клиент для персистентного хранения
        self.supabase = supabase_client

        # Использовать абсолютный путь для stats файла (fallback)
        if stats_file is None:
            # Получить директорию где находится app.py
            base_dir = os.path.dirname(os.path.abspath(__file__))
            stats_file = os.path.join(base_dir, 'data', 'stats.json')

        self.stats_file = stats_file
        logger.info(f"📂 Stats file path: {self.stats_file}")

        # Создать директорию data/ если не существует
        try:
            stats_dir = os.path.dirname(self.stats_file)
            os.makedirs(stats_dir, exist_ok=True)
            logger.info(f"📂 Stats directory created/verified: {stats_dir}")
        except Exception as e:
            logger.error(f"❌ Ошибка создания директории {stats_dir}: {str(e)}")

        # Новое: отслеживание ошибок (будет загружено из Supabase или файла)
        self.total_requests_today = 0
        self.successful_requests_today = 0
        self.failed_requests_today = 0
        self.error_breakdown = {}  # {429: count, 403: count, ...}
        self.languages_today = {}  # {en: count, ru: count, ...}
        self.daily_reset_time = self._get_reset_time()

        # Загрузить статистику из Supabase или файла
        self._load_stats()

    def _get_reset_time(self):
        """Получить время когда нужно сбросить дневную статистику (00:00 UTC)"""
        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)
        reset_time = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        return reset_time.timestamp()

    def _load_stats(self):
        """Загрузить статистику из Supabase (приоритет) или JSON файла (fallback)"""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        # Попытка 1: Загрузить из Supabase
        if self.supabase:
            try:
                response = self.supabase.table('daily_stats').select('*').eq('date', today).execute()
                if response.data and len(response.data) > 0:
                    data = response.data[0]
                    self.total_requests_today = data.get('total_requests', 0)
                    self.successful_requests_today = data.get('successful', 0)
                    self.failed_requests_today = data.get('failed', 0)
                    self.error_breakdown = data.get('error_breakdown', {})
                    self.languages_today = data.get('languages', {})
                    logger.info(f"✅ Статистика загружена из Supabase: {self.total_requests_today} запросов за сегодня")
                    return
                else:
                    logger.info(f"ℹ️ Данных за {today} в Supabase нет, начинаем с нуля")
                    return
            except Exception as e:
                logger.warning(f"⚠️ Ошибка загрузки из Supabase: {str(e)}, пытаемся JSON")

        # Попытка 2: Загрузить из JSON файла (fallback)
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)

                # Проверить что данные за сегодняшний день
                saved_date = data.get('date', '')

                if saved_date == today:
                    # Данные актуальны - загружаем
                    self.total_requests_today = data.get('total_requests', 0)
                    self.successful_requests_today = data.get('successful', 0)
                    self.failed_requests_today = data.get('failed', 0)
                    self.error_breakdown = data.get('error_breakdown', {})
                    self.languages_today = data.get('languages', {})
                    self.daily_reset_time = data.get('daily_reset_time', self._get_reset_time())
                    logger.info(f"✅ Статистика загружена из JSON: {self.total_requests_today} запросов за сегодня")
                else:
                    # Данные устарели - начинаем с нуля
                    logger.info(f"ℹ️ Статистика устарела ({saved_date} != {today}), начинаем новый день")
                    self._reset_daily_stats()
            else:
                logger.info("ℹ️ Файл статистики не найден, начинаем с нуля")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки статистики из JSON: {str(e)}")
            logger.error(f"📋 Stack trace: {traceback.format_exc()}")

    def _save_stats(self):
        """Сохранить статистику в Supabase (приоритет) и JSON файл (fallback)"""
        logger.info(f"🔍 DEBUG: _save_stats вызван - total={self.total_requests_today}, successful={self.successful_requests_today}, languages={self.languages_today}")

        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        data = {
            'date': today,
            'total_requests': self.total_requests_today,
            'successful': self.successful_requests_today,
            'failed': self.failed_requests_today,
            'error_breakdown': self.error_breakdown,
            'languages': self.languages_today
        }

        # Попытка 1: Сохранить в Supabase (upsert - создать или обновить)
        if self.supabase:
            try:
                self.supabase.table('daily_stats').upsert(data).execute()
                # Логировать сохранение (но не на каждый запрос - слишком много логов)
                if self.total_requests_today % 10 == 0 or self.total_requests_today <= 3:
                    logger.info(f"💾 Статистика сохранена в Supabase: {self.total_requests_today} запросов")
            except Exception as e:
                logger.error(f"❌ Ошибка сохранения в Supabase: {str(e)}")

        # Попытка 2: Сохранить в JSON (всегда, как fallback)
        try:
            data['daily_reset_time'] = self.daily_reset_time
            data['last_updated'] = time.time()

            with open(self.stats_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения в JSON: {str(e)}")
            logger.error(f"📋 Stack trace: {traceback.format_exc()}")

    def log_youtube_request(self, video_id, endpoint, lang=None, status='success',
                           response_time_ms=0, error_type=None, status_code=None):
        """Логировать запрос к YouTube"""
        logger.info(f"🔍 DEBUG: log_youtube_request вызван - video_id={video_id}, lang={lang}, status={status}")
        with self.lock:
            now = time.time()

            # Сбросить счетчик если прошла минута
            if now - self.last_reset_minute > 60:
                self.requests_per_minute = 0
                self.last_reset_minute = now

            # Сбросить счетчик если прошел час
            if now - self.last_reset_hour > 3600:
                self.requests_per_hour = 0
                self.last_reset_hour = now

            # Сбросить дневную статистику если прошли сутки
            if now > self.daily_reset_time:
                self._reset_daily_stats()
                self.daily_reset_time = self._get_reset_time()

            self.requests_per_minute += 1
            self.requests_per_hour += 1

            # Новое: дневная статистика
            self.total_requests_today += 1
            if status == 'success':
                self.successful_requests_today += 1
            else:
                self.failed_requests_today += 1

            # Логировать в список
            request_info = {
                'timestamp': now,
                'video_id': video_id,
                'endpoint': endpoint,
                'lang': lang,
                'status': status,
                'response_time_ms': response_time_ms,
                'error_type': error_type,
                'status_code': status_code
            }
            self.request_log.append(request_info)

            # Хранить только последние 100 запросов
            if len(self.request_log) > 100:
                self.request_log.pop(0)

            # Подсчет ошибок по типам
            if error_type:
                error_key = f"{status_code}" if status_code else error_type
                self.error_breakdown[error_key] = self.error_breakdown.get(error_key, 0) + 1

            # Подсчет языков
            if lang:
                self.languages_today[lang] = self.languages_today.get(lang, 0) + 1

            # Сохранить статистику в файл
            self._save_stats()

            # ⚠️ Предупреждение если слишком много запросов
            if self.requests_per_minute > 10:
                logger.warning(f"⚠️ ВНИМАНИЕ: {self.requests_per_minute} запросов в минуту! YouTube может заблокировать!")

            if self.requests_per_hour > 100:
                logger.error(f"🔴 КРИТИЧНО: {self.requests_per_hour} запросов в час! YouTube заблокирует!")

    def _reset_daily_stats(self):
        """Сброс дневной статистики"""
        self.total_requests_today = 0
        self.successful_requests_today = 0
        self.failed_requests_today = 0
        self.error_breakdown = {}
        self.languages_today = {}
        # Сохранить сброшенную статистику в файл
        self._save_stats()

    def get_stats(self):
        """Получить статистику"""
        with self.lock:
            return {
                'requests_per_minute': self.requests_per_minute,
                'requests_per_hour': self.requests_per_hour,
                'recent_requests': self.request_log[-10:],
                'status': self._get_health_status(),
                'error_breakdown': self.error_breakdown.copy(),
                'total_requests_today': self.total_requests_today,
                'successful_requests_today': self.successful_requests_today,
                'failed_requests_today': self.failed_requests_today,
                'languages_today': self.languages_today.copy()
            }

    def get_daily_stats(self):
        """Получить дневную статистику"""
        with self.lock:
            success_rate = 0.0
            if self.total_requests_today > 0:
                success_rate = (self.successful_requests_today / self.total_requests_today) * 100

            return {
                'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                'total_requests': self.total_requests_today,
                'successful': self.successful_requests_today,
                'failed': self.failed_requests_today,
                'success_rate': success_rate,
                'error_breakdown': self.error_breakdown.copy(),
                'languages': self.languages_today.copy()
            }

    def _get_health_status(self):
        """Определить здоровье системы"""
        if error_tracker.has_429() or error_tracker.consecutive_failures >= 8:
            return 'blocked'
        elif error_tracker.has_403() or error_tracker.consecutive_failures >= 5:
            return 'critical'
        elif self.requests_per_minute > 10 or self.failed_requests_today > 20:
            return 'warning'
        else:
            return 'healthy'

# Глобальный монитор запросов (будет инициализирован после Supabase)
request_monitor = None

# ============================================================================
# NOTIFICATION MANAGER (Telegram + Email)
# ============================================================================

class NotificationManager:
    """
    Управляет отправкой уведомлений в Telegram
    """
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        self.enabled = os.getenv('ENABLE_TELEGRAM_ALERTS', 'true').lower() == 'true'

        self.last_alert_time = {}  # {alert_type: timestamp}
        try:
            self.alert_debounce_minutes = int(os.getenv('ALERT_DEBOUNCE_MINUTES', '5'))
        except (ValueError, TypeError):
            self.alert_debounce_minutes = 5
        self.lock = threading.Lock()

    def send_telegram_alert(self, severity, message):
        """Отправить алерт в Telegram (асинхронно в background)"""
        if not self.enabled or not self.telegram_token or not self.telegram_chat_id:
            logger.warning("⚠️ Telegram не настроен (TOKEN или CHAT_ID отсутствуют)")
            return

        # Проверить дебаунсинг (не отправлять часто)
        with self.lock:
            if severity in self.last_alert_time:
                elapsed = time.time() - self.last_alert_time[severity]
                if elapsed < self.alert_debounce_minutes * 60:
                    logger.info(f"ℹ️ Пропуск дублирующегося алерта {severity} (дебаунсинг)")
                    return

            self.last_alert_time[severity] = time.time()

        # Отправить в фоне (не блокировать главный поток)
        threading.Thread(
            target=self._send_telegram_background,
            args=(severity, message),
            daemon=True
        ).start()

    def _send_telegram_background(self, severity, message):
        """Отправить сообщение в Telegram (фоновый поток)"""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"

            # Форматирование сообщения
            formatted_message = self._format_message(severity, message)

            payload = {
                'chat_id': self.telegram_chat_id,
                'text': formatted_message,
                'parse_mode': 'HTML'
            }

            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                logger.info(f"✅ Telegram алерт отправлен ({severity})")
            else:
                logger.error(f"❌ Ошибка отправки Telegram: {response.text}")

        except Exception as e:
            logger.error(f"❌ Ошибка при отправке в Telegram: {str(e)}")

    def _format_message(self, severity, message):
        """Форматировать сообщение для Telegram"""
        if isinstance(message, dict):
            # Форматировать из словаря
            formatted = self._format_alert_dict(severity, message)
        else:
            # Строка
            formatted = str(message)

        return formatted

    def _format_alert_dict(self, severity, data):
        """Форматировать алерт из словаря"""
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

        if severity == 'blocked':
            return f"""🚨 <b>YOUTUBE БЛОКИРОВКА ОБНАРУЖЕНА!</b>

<b>⚠️ СТАТУС:</b> BLOCKED (полная блокировка)
├─ HTTP код: {data.get('status_code', 'N/A')}
├─ Ошибок подряд: {data.get('consecutive_failures', 'N/A')}
└─ Error rate: {data.get('error_rate', 0):.1f}%

<b>🔴 РИСК:</b> КРИТИЧНЫЙ ({data.get('risk_score', 0)}/100)

<b>⏱️ ДЕЙСТВУЙТЕ НЕМЕДЛЕННО:</b>
1. Включить proxy сервис
2. Или перезагрузить на Railway
3. Проверить /api/status

Время: {timestamp}"""

        elif severity == 'critical':
            return f"""🔴 <b>КРИТИЧНАЯ ОШИБКА!</b>

<b>⚠️ СТАТУС:</b> CRITICAL
├─ HTTP код: {data.get('status_code', 'N/A')}
├─ Ошибок подряд: {data.get('consecutive_failures', 'N/A')}
└─ Error rate: {data.get('error_rate', 0):.1f}%

<b>🟠 РИСК:</b> ВЫСОКИЙ ({data.get('risk_score', 0)}/100)

<b>⏱️ Действуйте быстро (15 минут):</b>
1. Включить proxy
2. Или снизить нагрузку

Время: {timestamp}"""

        elif severity == 'warning':
            return f"""⚠️ <b>ВНИМАНИЕ!</b>

<b>📊 СТАТУС:</b> WARNING
├─ Error rate: {data.get('error_rate', 0):.1f}%
└─ HTTP 429 detected: {data.get('has_429', False)}

<b>🟡 РИСК:</b> СРЕДНИЙ ({data.get('risk_score', 0)}/100)

<b>💡 Рекомендация:</b>
Включить proxy в течение часа

Время: {timestamp}"""

        else:
            return str(data)

# Глобальный менеджер уведомлений (инициализируется позже)
notification_manager = None

# ============================================================================
# BLOCKAGE DETECTOR (обнаружение блокировки)
# ============================================================================

class BlockageDetector:
    """
    Анализирует паттерны ошибок и определяет риск блокировки YouTube
    """
    def __init__(self):
        self.last_risk_score = 0
        self.last_severity = 'healthy'
        self.consecutive_critical_alerts = 0
        self.lock = threading.Lock()

    def calculate_risk_score(self):
        """Вычислить risk score (0-100)"""
        with self.lock:
            score = 0

            # HTTP 429 - максимальный приоритет
            if error_tracker.has_429():
                score += 100
                logger.error("🔴 HTTP 429 обнаружена - критическая блокировка!")

            # HTTP 403
            if error_tracker.has_403():
                score += 80
                logger.warning("🟠 HTTP 403 обнаружена - предупреждение")

            # Ошибки подряд
            consecutive = error_tracker.consecutive_failures
            if consecutive >= 8:
                score += 50
            elif consecutive >= 5:
                score += 30
            elif consecutive >= 3:
                score += 10

            # Error rate
            stats = request_monitor.get_stats()
            total = stats.get('total_requests_today', 0) or stats.get('requests_per_hour', 0)
            failed = stats.get('failed_requests_today', 0)

            if total > 10:
                error_rate = (failed / total) * 100
                if error_rate > 50:
                    score += 20
                elif error_rate > 20:
                    score += 10

            # Ограничить максимум 100
            score = min(score, 100)
            self.last_risk_score = score

            return score

    def get_severity(self):
        """Определить severity уровень"""
        score = self.last_risk_score

        if error_tracker.has_429() or error_tracker.consecutive_failures >= 8:
            return 'blocked'
        elif error_tracker.has_403() or error_tracker.consecutive_failures >= 5 or score >= 50:
            return 'critical'
        elif score >= 20:
            return 'warning'
        else:
            return 'healthy'

    def should_send_alert(self):
        """Нужно ли отправить алерт?"""
        with self.lock:
            severity = self.get_severity()

            # Всегда отправляем critical и выше
            if severity in ['critical', 'blocked']:
                return True, severity

            # Warning отправляем 1 раз
            if severity == 'warning' and self.last_severity != 'warning':
                return True, severity

            return False, severity

# Глобальный детектор (инициализируется позже)
blockage_detector = None

# ============================================================================
# DAILY REPORT GENERATOR
# ============================================================================

def generate_daily_report():
    """Генерировать и отправить ежедневный отчет"""
    try:
        if not notification_manager:
            logger.warning("⚠️ NotificationManager не инициализирован, пропуск отчета")
            return

        stats = request_monitor.get_daily_stats()

        # Сформировать сообщение (даже если 0 запросов)
        top_langs = sorted(stats['languages'].items(), key=lambda x: x[1], reverse=True)[:3]
        top_errors = sorted(stats['error_breakdown'].items(), key=lambda x: x[1], reverse=True)

        langs_str = '\n'.join([f"   🌍 {lang}: {count}" for lang, count in top_langs]) if top_langs else "   Нет данных"
        errors_str = '\n'.join([f"   ❌ {error}: {count}" for error, count in top_errors]) if top_errors else "   Нет ошибок ✅"

        message = f"""📊 <b>ЕЖЕДНЕВНЫЙ ОТЧЕТ | {stats['date']}</b>

<b>✅ СТАТИСТИКА:</b>
   Всего: {stats['total_requests']}
   Успешно: {stats['successful']} ({stats['success_rate']:.1f}%)
   Ошибок: {stats['failed']}

<b>🌍 ТОП ЯЗЫКИ:</b>
{langs_str}

<b>⚠️ ОШИБКИ:</b>
{errors_str}

<b>🟢 YOUTUBE:</b> HEALTHY
Рекомендация: Все хорошо 👍"""

        # Отправить
        notification_manager.send_telegram_alert('daily_report', message)
        logger.info(f"📊 Ежедневный отчет отправлен (запросов за день: {stats['total_requests']})")

        # Сбросить статистику для нового дня
        request_monitor._reset_daily_stats()

    except Exception as e:
        logger.error(f"❌ Ошибка при генерировании отчета: {str(e)}")

# ============================================================================
# ИНИЦИАЛИЗАЦИЯ FLASK
# ============================================================================
app = Flask(__name__)

# ============================================================================
# ИНИЦИАЛИЗАЦИЯ ПЛАНИРОВЩИКА для ежедневных отчетов
# ============================================================================

def init_scheduler():
    """Инициализировать APScheduler для ежедневных отчетов"""
    if os.getenv('ENABLE_DAILY_REPORTS', 'true').lower() != 'true':
        logger.info("ℹ️ Ежедневные отчеты отключены")
        return

    try:
        scheduler = BackgroundScheduler(daemon=True)

        # Получить время из переменных окружения (по умолчанию 18:00 UTC)
        report_time = os.getenv('DAILY_REPORT_TIME', '18:00')
        hour, minute = map(int, report_time.split(':'))

        # Зарегистрировать задачу
        scheduler.add_job(
            func=generate_daily_report,
            trigger=CronTrigger(hour=hour, minute=minute, timezone='UTC'),
            id='daily_report',
            name='Daily Statistics Report',
            replace_existing=True
        )

        scheduler.start()
        logger.info(f"✅ APScheduler запущен. Ежедневный отчет в {report_time} UTC")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка инициализации scheduler: {str(e)}")

# Инициализировать scheduler
init_scheduler()

# ============================================================================
# ИНИЦИАЛИЗАЦИЯ МОНИТОРИНГА (отложенная, чтобы избежать build-time errors)
# ============================================================================

def init_monitoring():
    """Инициализировать систему мониторинга при запуске приложения"""
    global notification_manager, blockage_detector

    try:
        notification_manager = NotificationManager()
        blockage_detector = BlockageDetector()
        logger.info("✅ Система мониторинга инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации мониторинга: {str(e)}")

# Инициализировать мониторинг
init_monitoring()

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

# ============================================================================
# ИНИЦИАЛИЗАЦИЯ SUPABASE (для персистентного хранения статистики)
# ============================================================================
supabase_client = None
if SUPABASE_AVAILABLE:
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    if supabase_url and supabase_key:
        try:
            supabase_client: Client = create_client(supabase_url, supabase_key)
            logger.info("✅ Supabase client инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Supabase: {str(e)}")
    else:
        logger.warning("⚠️ SUPABASE_URL или SUPABASE_KEY не установлены - используется JSON файл")

# ============================================================================
# ИНИЦИАЛИЗАЦИЯ REQUEST MONITOR (после Supabase)
# ============================================================================
request_monitor = RequestMonitor(supabase_client=supabase_client)

# ============================================================================
# КОНФИГУРАЦИЯ ПРОКСИ ДЛЯ WEBSHARE (решает проблему блокировки Railway IP)
# ============================================================================
WEBSHARE_USERNAME = os.getenv('WEBSHARE_PROXY_USERNAME', None)  # например "hhlnixdt-residential-1"
WEBSHARE_PASSWORD = os.getenv('WEBSHARE_PROXY_PASSWORD', None)  # например "54tssmyl37of"

# Создаем YouTube API client с Webshare Rotating Residential прокси
youtube_api = None
proxy_enabled = False

if WEBSHARE_USERNAME and WEBSHARE_PASSWORD:
    try:
        # WebshareProxyConfig автоматически использует rotating residential прокси
        # через endpoint p.webshare.io:80 с автоматической ротацией IP
        proxy_config = WebshareProxyConfig(
            proxy_username=WEBSHARE_USERNAME,
            proxy_password=WEBSHARE_PASSWORD
        )
        youtube_api = YouTubeTranscriptApi(proxy_config=proxy_config)
        proxy_enabled = True
        logger.info(f"✅ Webshare Rotating Residential прокси настроен: {WEBSHARE_USERNAME}")
        logger.info("🔄 IP адрес будет автоматически ротироваться на каждый запрос")
        logger.info("🔒 YouTube запросы защищены от блокировки")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации WebshareProxyConfig: {str(e)}")
        logger.warning("⚠️ Используем обычный API без прокси")
        youtube_api = YouTubeTranscriptApi()
else:
    logger.warning("⚠️ Webshare прокси не настроен - используется прямое подключение к YouTube")
    logger.warning("⚠️ Установите переменные окружения: WEBSHARE_PROXY_USERNAME, WEBSHARE_PROXY_PASSWORD")
    logger.warning("⚠️ Без прокси Railway IP может быть заблокирован YouTube")
    youtube_api = YouTubeTranscriptApi()

# ============================================================================
# ИНИЦИАЛИЗАЦИЯ RATE LIMITER (адаптивная стратегия)
# ============================================================================
# С rotating residential proxy - нет задержки (каждый запрос с разного IP)
# Без proxy - задержка 0.5 сек для защиты от блокировки
min_interval = 0.0 if proxy_enabled else 0.5
youtube_rate_limiter = YouTubeRateLimiter(min_interval=min_interval)

if proxy_enabled:
    logger.info("⚡ Rate limiter: БЕЗ задержки (rotating residential proxy активен)")
else:
    logger.info(f"⏱️ Rate limiter: {min_interval}сек задержка (без proxy - защита от блокировки)")

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def get_first_available_transcript(transcript_list):
    """
    Получить первый доступный транскрипт с приоритизацией английского языка.

    Стратегия приоритизации:
    1. Ищем английский язык (en, en-US, en-GB и т.д.)
    2. Если нет - берем первый доступный язык

    Это решает проблему когда видео имеет несколько звуковых дорожек
    (например en, fr, es) и YouTube возвращает субтитры не на оригинальном языке.
    """
    # Приоритет 1: Английский язык в вручную созданных субтитрах
    if hasattr(transcript_list, '_manually_created_transcripts'):
        manually_created = getattr(transcript_list, '_manually_created_transcripts', {})
        if manually_created:
            # Ищем английский язык (любой вариант: en, en-US, en-GB)
            for lang_code in manually_created.keys():
                if lang_code.startswith('en'):
                    transcript = manually_created[lang_code]
                    logger.info(f"✅ Found English transcript: {transcript.language_code} ({transcript.language})")
                    return transcript

            # Если английского нет - берем первый доступный
            first_transcript = next(iter(manually_created.values()))
            logger.info(f"✅ Found manually created transcript (no English): {first_transcript.language_code}")
            return first_transcript

    # Приоритет 2: Английский язык в автоматически сгенерированных субтитрах
    if hasattr(transcript_list, '_generated_transcripts'):
        generated = getattr(transcript_list, '_generated_transcripts', {})
        if generated:
            # Ищем английский язык
            for lang_code in generated.keys():
                if lang_code.startswith('en'):
                    transcript = generated[lang_code]
                    logger.info(f"✅ Found English auto-generated transcript: {transcript.language_code}")
                    return transcript

            # Если английского нет - берем первый доступный
            first_transcript = next(iter(generated.values()))
            logger.info(f"✅ Found auto-generated transcript (no English): {first_transcript.language_code}")
            return first_transcript

    # Fallback для старых версий API
    if hasattr(transcript_list, 'manually_created_transcripts') and transcript_list.manually_created_transcripts:
        for transcript in transcript_list.manually_created_transcripts:
            if transcript.language_code.startswith('en'):
                logger.info(f"✅ Found English transcript (old API): {transcript.language_code}")
                return transcript
        logger.info(f"✅ Found {len(transcript_list.manually_created_transcripts)} manually created transcripts (old API)")
        return transcript_list.manually_created_transcripts[0]

    if hasattr(transcript_list, 'automatically_generated_transcripts') and transcript_list.automatically_generated_transcripts:
        for transcript in transcript_list.automatically_generated_transcripts:
            if transcript.language_code.startswith('en'):
                logger.info(f"✅ Found English transcript (old API): {transcript.language_code}")
                return transcript
        logger.info(f"✅ Found {len(transcript_list.automatically_generated_transcripts)} auto-generated transcripts (old API)")
        return transcript_list.automatically_generated_transcripts[0]

    # Если ничего не нашли, вернем None
    logger.error(f"❌ No transcripts found for video")
    return None


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
        # Получаем список транскриптов через инстанс API (с прокси)
        transcript_list = youtube_api.list(video_id)

        # Доступные языки (с автоматическими субтитрами и без)
        languages = []

        # Вручную созданные субтитры (новая версия API использует _manually_created_transcripts)
        if hasattr(transcript_list, '_manually_created_transcripts'):
            try:
                manually_created = getattr(transcript_list, '_manually_created_transcripts', {})
                for lang_code, transcript in manually_created.items():
                    languages.append({
                        "code": transcript.language_code,
                        "name": transcript.language,
                        "isAuto": False
                    })
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при обработке вручную созданных субтитров: {str(e)}")
        # Fallback для старых версий API
        elif hasattr(transcript_list, 'manually_created_transcripts') and transcript_list.manually_created_transcripts:
            try:
                for transcript in transcript_list.manually_created_transcripts:
                    languages.append({
                        "code": transcript.language_code,
                        "name": transcript.language,
                        "isAuto": False
                    })
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при обработке вручную созданных субтитров: {str(e)}")

        # Автоматически сгенерированные субтитры (новая версия API использует _generated_transcripts)
        if hasattr(transcript_list, '_generated_transcripts'):
            try:
                generated = getattr(transcript_list, '_generated_transcripts', {})
                for lang_code, transcript in generated.items():
                    languages.append({
                        "code": transcript.language_code,
                        "name": transcript.language,
                        "isAuto": True
                    })
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при обработке автоматических субтитров: {str(e)}")
        # Fallback для старых версий API
        elif hasattr(transcript_list, 'automatically_generated_transcripts') and transcript_list.automatically_generated_transcripts:
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "v2.0-debug-logging",  # Version marker to verify deployment
        "stats_file": request_monitor.stats_file if request_monitor else None
    }), 200


@app.route('/api/subtitles', methods=['POST'])
def get_subtitles():
    """
    ⚠️ ЭКСПЕРИМЕНТАЛЬНЫЙ ENDPOINT - В РАЗРАБОТКЕ
    ⚠️ НЕ ИСПОЛЬЗУЕТСЯ Chrome расширением

    Основной endpoint для расширения: GET /api/subtitles/<video_id>

    Этот endpoint поддерживает дополнительные возможности:
    - Выбор конкретного языка субтитров
    - Перевод субтитров на другой язык (функция работает, но требует тестирования)

    Request:
    {
        "videoId": "E19_kwN0f38",
        "language": "en",
        "translateTo": null  // или "ru" для перевода
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
        start_time = time.time()
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
            list_start = time.time()
            logger.info(f"📡 Запрашиваем список транскриптов для видео {video_id}...")

            # Rate limiting перед YouTube API вызовом
            youtube_rate_limiter.wait_if_needed()

            # Получаем список транскриптов через API инстанс (с прокси)
            transcript_list = youtube_api.list(video_id)

            list_duration = time.time() - list_start
            logger.info(f"✅ Получен список транскриптов для {video_id} ({list_duration:.2f}сек)")

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
            fetch_start = time.time()
            if translate_to and translate_to != language:
                logger.info(f"🌐 Переводим субтитры на {translate_to}")
                try:
                    translated = transcript.translate(translate_to)
                    # Rate limiting перед fetch YouTube API вызовом
                    youtube_rate_limiter.wait_if_needed()
                    subtitle_data = translated.fetch()
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка перевода на {translate_to}, используем оригинал: {str(e)}")
                    # Rate limiting перед fetch YouTube API вызовом
                    youtube_rate_limiter.wait_if_needed()
                    subtitle_data = transcript.fetch()
            else:
                # Rate limiting перед fetch YouTube API вызовом
                youtube_rate_limiter.wait_if_needed()
                subtitle_data = transcript.fetch()

            fetch_duration = time.time() - fetch_start
            logger.info(f"⏱️ Fetch сек: {fetch_duration:.2f}сек")

            # Форматируем субтитры
            format_start = time.time()
            formatted_subtitles = format_subtitles(subtitle_data)
            format_duration = time.time() - format_start

            total_duration = time.time() - start_time
            logger.info(f"✅ Успешно получены {len(formatted_subtitles)} субтитров за {total_duration:.2f}сек (список: {list_duration:.2f}с, fetch: {fetch_duration:.2f}с, формат: {format_duration:.2f}с)")
            logger.info(f"🔍 DEBUG: После успешного получения, video_id={video_id}, language={language}")

            # Получаем реальный язык который был использован
            actual_language = transcript.language_code if hasattr(transcript, 'language_code') else language

            # ✅ ПОСЛЕ успешного получения субтитров
            logger.info(f"🔍 DEBUG: Перед вызовом error_tracker.reset_consecutive_failures()")
            error_tracker.reset_consecutive_failures()  # Сброс счетчика ошибок
            logger.info(f"🔍 DEBUG: Перед вызовом request_monitor.log_youtube_request()")
            request_monitor.log_youtube_request(
                video_id, 'POST', lang=language,
                status='success',
                response_time_ms=int(total_duration * 1000)
            )
            logger.info(f"🔍 DEBUG: ПОСЛЕ вызова request_monitor.log_youtube_request()")

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
            request_monitor.log_youtube_request(
                video_id, 'POST', lang=language,
                status='error',
                error_type='TranscriptsDisabled',
                status_code=403
            )
            return jsonify({
                "success": False,
                "error": "Transcripts are disabled for this video"
            }), 403

        except VideoUnavailable:
            logger.error(f"❌ Видео недоступно: {video_id}")
            request_monitor.log_youtube_request(
                video_id, 'POST', lang=language,
                status='error',
                error_type='VideoUnavailable',
                status_code=404
            )
            return jsonify({
                "success": False,
                "error": "Video is unavailable"
            }), 404

        except Exception as e:
            logger.error(f"❌ Ошибка получения субтитров: {str(e)}")

            # 🆕 НОВОЕ: Отслеживание ошибок и отправка алертов
            error_type = type(e).__name__
            status_code = getattr(e, 'status_code', None)

            error_tracker.record_error(
                error_type=error_type,
                status_code=status_code,
                response_text=str(e),
                video_id=video_id
            )

            request_monitor.log_youtube_request(
                video_id, 'POST', lang=language,
                status='error',
                error_type=error_type,
                status_code=status_code
            )

            # Проверить нужно ли отправить алерт
            if blockage_detector and notification_manager:
                risk_score = blockage_detector.calculate_risk_score()
                should_alert, severity = blockage_detector.should_send_alert()

                if should_alert:
                    alert_data = {
                        'status_code': status_code,
                        'error_type': error_type,
                        'consecutive_failures': error_tracker.consecutive_failures,
                        'error_rate': (request_monitor.failed_requests_today / max(request_monitor.total_requests_today, 1)) * 100,
                        'risk_score': risk_score,
                        'has_429': error_tracker.has_429(),
                        'has_403': error_tracker.has_403()
                    }
                    notification_manager.send_telegram_alert(severity, alert_data)

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
    ✅ ОСНОВНОЙ ENDPOINT - ИСПОЛЬЗУЕТСЯ CHROME РАСШИРЕНИЕМ

    GET эндпоинт для получения субтитров.
    Всегда возвращает ОРИГИНАЛЬНЫЙ язык видео (параметр lang игнорируется).
    Простой, быстрый, без перевода.

    Формат ответа: {index, start, end, dur, text}

    Query Parameters:
    - lang: язык субтитров (ИГНОРИРУЕТСЯ - всегда возвращается оригинальный язык)
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
        start_time = time.time()
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
        # Параметр lang игнорируется - всегда возвращаем оригинальный язык видео
        response_format = request.args.get('format', 'json').strip()

        logger.info(f"📥 GET запрос: видео {video_id} (lang параметр игнорируется - возвращаем оригинальный язык)")

        # ===== ПОЛУЧЕНИЕ СУБТИТРОВ =====
        try:
            # Получаем список доступных транскриптов
            list_start = time.time()
            # Rate limiting перед YouTube API вызовом
            youtube_rate_limiter.wait_if_needed()

            # Получаем список транскриптов через API инстанс (с прокси)
            transcript_list = youtube_api.list(video_id)

            list_duration = time.time() - list_start
            logger.info(f"✅ Получен список транскриптов для {video_id} ({list_duration:.2f}сек)")

            # Получаем первый доступный язык (оригинальный язык видео)
            # Это не требует дополнительных YouTube API запросов
            transcript = get_first_available_transcript(transcript_list)

            if transcript is None:
                logger.error(f"❌ Нет ни одного доступного транскрипта для видео")
                return jsonify({
                    "success": False,
                    "status": "error",
                    "error": "No subtitles available for this video",
                    "videoId": video_id,
                    "count": 0,
                    "subtitles": []
                }), 200

            logger.info(f"✅ Получаем субтитры на оригинальном языке: {transcript.language_code if hasattr(transcript, 'language_code') else 'unknown'}")

            # Получаем субтитры
            fetch_start = time.time()
            # Rate limiting перед fetch YouTube API вызовом
            youtube_rate_limiter.wait_if_needed()
            subtitle_data = transcript.fetch()

            fetch_duration = time.time() - fetch_start
            logger.info(f"⏱️ Fetch: {fetch_duration:.2f}сек")

            # Форматируем субтитры в требуемый формат
            formatted_subtitles = format_subtitles_for_extension(subtitle_data)

            total_duration = time.time() - start_time
            logger.info(f"✅ Успешно получены {len(formatted_subtitles)} субтитров за {total_duration:.2f}сек (список: {list_duration:.2f}с, fetch: {fetch_duration:.2f}с)")

            actual_language = transcript.language_code if hasattr(transcript, 'language_code') else 'unknown'

            # ✅ Логировать успешный запрос в статистику
            error_tracker.reset_consecutive_failures()
            request_monitor.log_youtube_request(
                video_id, 'GET', lang=actual_language,
                status='success',
                response_time_ms=int(total_duration * 1000)
            )

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
            request_monitor.log_youtube_request(
                video_id, 'GET', lang=None,
                status='error',
                error_type='TranscriptsDisabled',
                status_code=403
            )
            return jsonify({
                "success": False,
                "status": "error",
                "error": "Transcripts are disabled for this video",
                "videoId": video_id,
                "count": 0,
                "subtitles": []
            }), 200

        except VideoUnavailable:
            logger.error(f"❌ Видео недоступно: {video_id}")
            request_monitor.log_youtube_request(
                video_id, 'GET', lang=None,
                status='error',
                error_type='VideoUnavailable',
                status_code=404
            )
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
# ТЕСТОВЫЕ ENDPOINT'Ы (с поддержкой параметра lang и мониторингом)
# ============================================================================

@app.route('/api/subtitles/test/<video_id>', methods=['GET'])
def get_subtitles_test(video_id):
    """
    🧪 ТЕСТОВЫЙ endpoint для GET с поддержкой параметра lang.

    Используйте для тестирования новой функциональности.
    Этот endpoint логирует все запросы к YouTube и помогает отслеживать нагрузку.

    URL: GET /api/subtitles/test/<videoId>?lang=<language>

    Параметры:
    - lang: опциональный язык субтитров (может быть auto-generated YouTube)

    Возвращает тот же формат что и основной GET endpoint.
    """
    try:
        start_time = time.time()
        video_id = video_id.strip()
        if not video_id or len(video_id) != 11:
            return jsonify({
                "success": False,
                "status": "error",
                "error": "Invalid video ID format. Must be 11 characters.",
                "videoId": video_id
            }), 400

        lang_param = request.args.get('lang', '').strip()
        logger.info(f"🧪 TEST запрос: видео {video_id}, язык {lang_param if lang_param else '(оригинальный)'}")

        try:
            # Rate limiting
            list_start = time.time()
            youtube_rate_limiter.wait_if_needed()

            # Получаем список транскриптов через API инстанс (с прокси)
            transcript_list = youtube_api.list(video_id)

            list_duration = time.time() - list_start
            logger.info(f"✅ Получен список транскриптов для {video_id} ({list_duration:.2f}сек)")

            # Логировать запрос в монитор
            request_monitor.log_youtube_request(video_id, 'GET_TEST', lang=lang_param)

            # Если указан язык - пытаемся найти его
            if lang_param:
                try:
                    transcript = transcript_list.find_transcript([lang_param])
                    logger.info(f"✅ Найдены субтитры на {lang_param}")
                except NoTranscriptFound:
                    logger.warning(f"⚠️ Язык {lang_param} не найден, возвращаем оригинальный")
                    transcript = get_first_available_transcript(transcript_list)
            else:
                # Возвращаем оригинальный язык
                transcript = get_first_available_transcript(transcript_list)

            if transcript is None:
                logger.error(f"❌ Нет ни одного доступного транскрипта для видео")
                return jsonify({
                    "success": False,
                    "status": "error",
                    "error": "No subtitles available for this video",
                    "videoId": video_id,
                    "count": 0,
                    "subtitles": []
                }), 200

            logger.info(f"✅ Получаем субтитры: {transcript.language_code if hasattr(transcript, 'language_code') else 'unknown'}")

            # Rate limiting перед fetch
            fetch_start = time.time()
            youtube_rate_limiter.wait_if_needed()
            subtitle_data = transcript.fetch()

            fetch_duration = time.time() - fetch_start
            logger.info(f"⏱️ Fetch: {fetch_duration:.2f}сек")

            # Логировать успех
            request_monitor.log_youtube_request(video_id, 'GET_TEST', lang=lang_param, status='success')

            formatted_subtitles = format_subtitles_for_extension(subtitle_data)
            actual_language = transcript.language_code if hasattr(transcript, 'language_code') else 'unknown'

            total_duration = time.time() - start_time
            logger.info(f"✅ Успешно получены {len(formatted_subtitles)} субтитров за {total_duration:.2f}сек (список: {list_duration:.2f}с, fetch: {fetch_duration:.2f}с)")

            return jsonify({
                "success": True,
                "status": "completed",
                "videoId": video_id,
                "language": actual_language,
                "requested_language": lang_param if lang_param else None,
                "count": len(formatted_subtitles),
                "subtitles": formatted_subtitles,
                "_test": True  # Маркер что это тестовый endpoint
            }), 200

        except TranscriptsDisabled:
            logger.error(f"❌ Субтитры отключены для видео {video_id}")
            request_monitor.log_youtube_request(video_id, 'GET_TEST', lang=lang_param, status='disabled')
            return jsonify({
                "success": False,
                "status": "error",
                "error": "Transcripts are disabled for this video",
                "videoId": video_id,
                "count": 0,
                "subtitles": []
            }), 200

        except VideoUnavailable:
            logger.error(f"❌ Видео недоступно: {video_id}")
            request_monitor.log_youtube_request(video_id, 'GET_TEST', lang=lang_param, status='not_found')
            return jsonify({
                "success": False,
                "status": "error",
                "error": "Video not found on YouTube",
                "videoId": video_id
            }), 404

        except Exception as e:
            logger.error(f"❌ Ошибка: {str(e)}")
            request_monitor.log_youtube_request(video_id, 'GET_TEST', lang=lang_param, status='error')
            return jsonify({
                "success": False,
                "status": "error",
                "error": f"Failed to fetch subtitles: {str(e)}",
                "videoId": video_id,
                "count": 0,
                "subtitles": []
            }), 200

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в /api/subtitles/test/<videoId>: {str(e)}")
        return jsonify({
            "success": False,
            "status": "error",
            "error": "Internal server error"
        }), 500


@app.route('/api/status', methods=['GET'])
def get_detailed_status():
    """
    Детальный статус здоровья сервера и YouTube блокировки
    """
    try:
        stats = request_monitor.get_stats()

        # Проверить что мониторинг инициализирован
        if blockage_detector:
            risk_score = blockage_detector.calculate_risk_score()
            severity = blockage_detector.get_severity()
        else:
            risk_score = 0
            severity = 'healthy'
            logger.warning("⚠️ BlockageDetector не инициализирован")

        daily_stats = request_monitor.get_daily_stats()

        return jsonify({
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z',

            "status": severity,
            "risk_score": risk_score,

            "youtube_metrics": {
                "requests_last_hour": stats['requests_per_hour'],
                "requests_last_minute": stats['requests_per_minute'],
                "error_rate": (daily_stats['failed'] / max(daily_stats['total_requests'], 1) * 100) if daily_stats['total_requests'] > 0 else 0,
                "http_429_detected": error_tracker.has_429(),
                "http_403_detected": error_tracker.has_403(),
                "consecutive_failures": error_tracker.consecutive_failures,
                "error_breakdown": stats['error_breakdown']
            },

            "daily_stats": {
                "date": daily_stats['date'],
                "total_requests": daily_stats['total_requests'],
                "successful": daily_stats['successful'],
                "failed": daily_stats['failed'],
                "success_rate": daily_stats['success_rate'],
                "top_languages": dict(sorted(daily_stats['languages'].items(),
                                             key=lambda x: x[1],
                                             reverse=True)[:5])
            },

            "alerts": [
                {
                    "time": datetime.utcfromtimestamp(req['timestamp']).isoformat() + 'Z',
                    "status_code": req['status_code'],
                    "error_type": req['error_type'],
                    "video_id": req['video_id']
                }
                for req in stats['recent_requests']
                if req['status'] != 'success'
            ],

            "recommendation": _get_recommendation(severity, risk_score)
        }), 200

    except Exception as e:
        logger.error(f"❌ Ошибка в /api/status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


def _get_recommendation(severity, risk_score):
    """Дать рекомендацию на основе severity"""
    if severity == 'blocked':
        return "🚨 КРИТИЧНО: YouTube полностью заблокировал сервер. Включите proxy немедленно или перезагрузитесь."
    elif severity == 'critical':
        return "🔴 СРОЧНО: Включите proxy в течение 15 минут, иначе YouTube заблокирует."
    elif severity == 'warning':
        return "⚠️ Включите proxy в течение часа, чтобы избежать блокировки."
    else:
        return "✅ Все хорошо, мониторинг включен."


@app.route('/api/send-report', methods=['POST', 'GET'])
def send_report_now():
    """
    🚀 Принудительная отправка ежедневного отчета в Telegram прямо сейчас

    Использование:
    - GET/POST /api/send-report

    Отправляет текущую статистику за день в Telegram (даже если 0 запросов)
    """
    try:
        if not notification_manager:
            return jsonify({
                "success": False,
                "error": "NotificationManager не инициализирован"
            }), 500

        if not notification_manager.telegram_token or not notification_manager.telegram_chat_id:
            return jsonify({
                "success": False,
                "error": "Telegram не настроен (TOKEN или CHAT_ID отсутствуют)"
            }), 400

        # Получить статистику
        stats = request_monitor.get_daily_stats()

        # Сформировать отчет (даже если 0 запросов)
        top_langs = sorted(stats['languages'].items(), key=lambda x: x[1], reverse=True)[:3]
        top_errors = sorted(stats['error_breakdown'].items(), key=lambda x: x[1], reverse=True)

        langs_str = '\n'.join([f"   🌍 {lang}: {count}" for lang, count in top_langs]) if top_langs else "   Нет данных"
        errors_str = '\n'.join([f"   ❌ {error}: {count}" for error, count in top_errors]) if top_errors else "   Нет ошибок ✅"

        # Добавить информацию о статусе системы
        if blockage_detector:
            risk_score = blockage_detector.calculate_risk_score()
            severity = blockage_detector.get_severity()
            status_emoji = {
                'healthy': '🟢',
                'warning': '🟡',
                'critical': '🟠',
                'blocked': '🔴'
            }.get(severity, '🟢')
            status_text = severity.upper()
        else:
            risk_score = 0
            status_emoji = '🟢'
            status_text = 'HEALTHY'

        message = f"""📊 <b>ЕЖЕДНЕВНЫЙ ОТЧЕТ | {stats['date']}</b>

<b>✅ СТАТИСТИКА:</b>
   Всего: {stats['total_requests']}
   Успешно: {stats['successful']} ({stats['success_rate']:.1f}%)
   Ошибок: {stats['failed']}

<b>🌍 ТОП ЯЗЫКИ:</b>
{langs_str}

<b>⚠️ ОШИБКИ:</b>
{errors_str}

<b>{status_emoji} YOUTUBE:</b> {status_text}
   Risk Score: {risk_score}/100
   Рекомендация: {_get_recommendation(severity, risk_score)}

<i>⚡ Отчет отправлен по запросу через /api/send-report</i>"""

        # Отправить (используем severity='info' чтобы не блокировался debounce)
        notification_manager.send_telegram_alert('manual_report', message)
        logger.info("📊 Ручной отчет отправлен через /api/send-report")

        return jsonify({
            "success": True,
            "message": "Report sent to Telegram",
            "stats": stats,
            "telegram_configured": True
        }), 200

    except Exception as e:
        logger.error(f"❌ Ошибка при отправке отчета: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/monitoring', methods=['GET'])
def get_monitoring():
    """
    📊 Endpoint мониторинга нагрузки на YouTube API.

    Возвращает статистику по запросам к YouTube для отслеживания проблем.
    """
    stats = request_monitor.get_stats()

    return jsonify({
        "success": True,
        "service": "YouTube Subtitles API Monitoring",
        "monitoring_data": {
            "requests_per_minute": stats['requests_per_minute'],
            "requests_per_hour": stats['requests_per_hour'],
            "status": stats['status'],
            "health_alerts": {
                "warning_at": 10,  # запросов в минуту
                "critical_at": 100  # запросов в час
            },
            "recent_requests": [
                {
                    "video_id": req['video_id'],
                    "endpoint": req['endpoint'],
                    "language": req['lang'],
                    "status": req['status'],
                    "time_ago": f"{int(time.time() - req['timestamp'])}s ago"
                }
                for req in stats['recent_requests']
            ]
        }
    }), 200


@app.route('/api/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """
    🤖 Telegram Webhook для обработки команд бота

    Поддерживаемые команды:
    - /stats или /status - получить текущую статистику за день
    - /help - список доступных команд
    """
    try:
        if not notification_manager or not notification_manager.telegram_token:
            return jsonify({"success": False, "error": "Telegram not configured"}), 400

        data = request.get_json()

        # Проверить что это сообщение
        if 'message' not in data:
            return jsonify({"success": True}), 200

        message = data['message']
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '').strip()

        # Проверить что chat_id совпадает с настроенным
        if str(chat_id) != notification_manager.telegram_chat_id:
            logger.warning(f"⚠️ Получено сообщение от неизвестного chat_id: {chat_id}")
            return jsonify({"success": True}), 200

        logger.info(f"📥 Telegram команда: {text} от chat_id: {chat_id}")

        # Обработка команд
        if text in ['/stats', '/status']:
            # Получить текущую статистику
            stats = request_monitor.get_daily_stats()

            # Сформировать отчет
            top_langs = sorted(stats['languages'].items(), key=lambda x: x[1], reverse=True)[:3]
            top_errors = sorted(stats['error_breakdown'].items(), key=lambda x: x[1], reverse=True)

            langs_str = '\n'.join([f"   🌍 {lang}: {count}" for lang, count in top_langs]) if top_langs else "   Нет данных"
            errors_str = '\n'.join([f"   ❌ {error}: {count}" for error, count in top_errors]) if top_errors else "   Нет ошибок ✅"

            # Статус системы
            if blockage_detector:
                risk_score = blockage_detector.calculate_risk_score()
                severity = blockage_detector.get_severity()
                status_emoji = {
                    'healthy': '🟢',
                    'warning': '🟡',
                    'critical': '🟠',
                    'blocked': '🔴'
                }.get(severity, '🟢')
                status_text = severity.upper()
            else:
                risk_score = 0
                status_emoji = '🟢'
                status_text = 'HEALTHY'

            current_time = datetime.now(timezone.utc).strftime('%H:%M:%S UTC')

            message_text = f"""📊 <b>СТАТИСТИКА | {stats['date']}</b>
<i>Запрос в {current_time}</i>

<b>✅ СТАТИСТИКА:</b>
   Всего: {stats['total_requests']}
   Успешно: {stats['successful']} ({stats['success_rate']:.1f}%)
   Ошибок: {stats['failed']}

<b>🌍 ТОП ЯЗЫКИ:</b>
{langs_str}

<b>⚠️ ОШИБКИ:</b>
{errors_str}

<b>{status_emoji} YOUTUBE:</b> {status_text}
   Risk Score: {risk_score}/100
   {_get_recommendation(severity, risk_score)}"""

            # Отправить ответ
            notification_manager._send_telegram_background('stats_request', message_text)
            logger.info(f"✅ Статистика отправлена в ответ на команду /stats")

        elif text == '/help':
            help_text = """🤖 <b>YouTube API Monitor Bot</b>

<b>Доступные команды:</b>
/stats - Получить текущую статистику за день
/status - То же что и /stats
/help - Показать это сообщение

<b>Автоматические отчеты:</b>
📊 Ежедневный отчет отправляется в 18:00 UTC"""

            notification_manager._send_telegram_background('help', help_text)
            logger.info(f"✅ Help отправлен в ответ на команду /help")

        else:
            # Неизвестная команда
            logger.info(f"ℹ️ Неизвестная команда: {text}")

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"❌ Ошибка в telegram webhook: {str(e)}")
        logger.error(f"📋 Stack trace: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


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
