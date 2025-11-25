# Railway Variables - Быстрая настройка

## Обязательные переменные для работы с Webshare прокси

В Railway → Settings → Variables добавьте:

```bash
# Из Webshare Proxy List (выберите любой "Working" прокси)
WEBSHARE_PROXY_ADDRESS=63.141.62.166:6459
WEBSHARE_PROXY_USERNAME=hhlnixdt
WEBSHARE_PROXY_PASSWORD=54tssmyl37of
```

**⚠️ Замените на свои данные из https://proxy.webshare.io/ → Static Residential → Proxy List**

## Опциональные переменные (для Telegram алертов)

```bash
# Telegram бот для уведомлений о блокировках
TELEGRAM_BOT_TOKEN=your_bot_token_from_BotFather
TELEGRAM_CHAT_ID=your_chat_id
ENABLE_TELEGRAM_ALERTS=true

# Настройка отчетов
ENABLE_DAILY_REPORTS=true
DAILY_REPORT_TIME=18:00
```

## Проверка после деплоя

После добавления переменных Railway перезапустит приложение. Проверьте логи:

✅ **Успешно:**
```
✅ Прокси настроен: hhlnixdt@63.141.62.166:6459
🔒 YouTube запросы будут идти через Webshare Static Residential прокси
```

❌ **Не настроено:**
```
⚠️ Прокси не настроен - используется прямое подключение к YouTube
```

---

📖 **Подробная документация**: см. `WEBSHARE_PROXY_SETUP.md`
