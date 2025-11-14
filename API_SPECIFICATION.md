# YouTube Subtitles API Specification

## 📡 Server Information

**Production Server URL:**
```
https://web-production-bd8bb.up.railway.app
```

**Health Check Endpoint:**
```
GET https://web-production-bd8bb.up.railway.app/api/health
```

---

## 🎯 Main API Endpoints

### 1. Get Subtitles

**Endpoint:** `POST /api/subtitles`

**Base URL:** `https://web-production-bd8bb.up.railway.app/api/subtitles`

**Request Headers:**
```
Content-Type: application/json
```

**Request Body:**
```json
{
  "videoId": "dQw4w9WgXcQ",
  "language": "en",
  "translateTo": null
}
```

**Parameters:**
- `videoId` (string, required) - YouTube video ID (11 characters)
  - Example: `dQw4w9WgXcQ` from URL `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
  - Must be exactly 11 characters

- `language` (string, required) - ISO 639-1 language code for subtitles
  - Examples: `en` (English), `ru` (Russian), `es` (Spanish), `fr` (French), `de` (German)
  - If requested language unavailable, API returns first available language

- `translateTo` (string or null, optional) - Translate subtitles to this language
  - Set to `null` or omit parameter if no translation needed
  - Currently not implemented (API returns original language)

**Success Response (200 OK):**
```json
{
  "success": true,
  "videoId": "dQw4w9WgXcQ",
  "language": "en",
  "translatedTo": null,
  "subtitles": [
    {
      "time": 1.36,
      "duration": 1.68,
      "text": "[♪♪♪]"
    },
    {
      "time": 18.64,
      "duration": 3.24,
      "text": "♪ We're no strangers to love ♪"
    },
    {
      "time": 22.88,
      "duration": 4.32,
      "text": "♪ You know the rules\nand so do I ♪"
    }
  ],
  "count": 61,
  "availableLanguages": []
}
```

**Response Fields:**
- `success` (boolean) - Always `true` for successful requests
- `videoId` (string) - The video ID that was requested
- `language` (string) - Language code of returned subtitles
- `translatedTo` (string|null) - Language translation was applied to (if any)
- `subtitles` (array) - Array of subtitle objects
  - `time` (number) - Start time in seconds (float)
  - `duration` (number) - Duration in seconds (float)
  - `text` (string) - Subtitle text (may contain newlines)
- `count` (number) - Total number of subtitle snippets
- `availableLanguages` (array) - List of available languages for the video (currently empty)

**Error Response (400 Bad Request):**
```json
{
  "success": false,
  "error": "Invalid videoId format (must be 11 characters)"
}
```

**Error Response (403 Forbidden):**
```json
{
  "success": false,
  "error": "Transcripts are disabled for this video"
}
```

**Error Response (404 Not Found):**
```json
{
  "success": false,
  "error": "Video is unavailable"
}
```

**Error Response (500 Internal Server Error):**
```json
{
  "success": false,
  "error": "Failed to fetch transcripts: [error message]"
}
```

---

### 2. Get Available Languages

**Endpoint:** `GET /api/languages/<video_id>`

**Base URL:** `https://web-production-bd8bb.up.railway.app/api/languages/dQw4w9WgXcQ`

**Parameters:**
- `video_id` (path parameter, required) - YouTube video ID (11 characters)

**Success Response (200 OK):**
```json
{
  "success": true,
  "videoId": "dQw4w9WgXcQ",
  "languages": []
}
```

**Note:** The `languages` array is currently returned empty. This is a known limitation. To get available languages, call `/api/subtitles` endpoint and check which language code works.

---

### 3. Health Check

**Endpoint:** `GET /api/health`

**Base URL:** `https://web-production-bd8bb.up.railway.app/api/health`

**Success Response (200 OK):**
```json
{
  "ok": true,
  "service": "YouTube Subtitles API",
  "timestamp": "2025-11-14T08:02:02.226321"
}
```

Used to verify server is running and responding.

---

## 📝 Example Requests

### JavaScript/Fetch
```javascript
const response = await fetch('https://web-production-bd8bb.up.railway.app/api/subtitles', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    videoId: 'dQw4w9WgXcQ',
    language: 'en',
    translateTo: null
  })
});

const data = await response.json();
console.log(data.subtitles);
```

### cURL
```bash
curl -X POST https://web-production-bd8bb.up.railway.app/api/subtitles \
  -H "Content-Type: application/json" \
  -d '{"videoId": "dQw4w9WgXcQ", "language": "en", "translateTo": null}'
```

### Python
```python
import requests

url = 'https://web-production-bd8bb.up.railway.app/api/subtitles'
payload = {
    'videoId': 'dQw4w9WgXcQ',
    'language': 'en',
    'translateTo': None
}

response = requests.post(url, json=payload)
data = response.json()
print(data['subtitles'])
```

---

## ⚠️ Important Notes

### Video ID Extraction
Extract the 11-character video ID from YouTube URL:
```
https://www.youtube.com/watch?v=dQw4w9WgXcQ
                                   ^^^^^^^^^^
                                   Video ID
```

If URL has timestamp (`&t=38s`), ignore it:
```
https://www.youtube.com/watch?v=Gv2fzC96Z40&t=38s
                                   ^^^^^^^^^^^
                                   Video ID (ignore &t=38s)
```

### Supported Languages
The API supports any language that YouTube provides subtitles for. Common ones:
- `en` - English
- `ru` - Russian
- `es` - Spanish
- `fr` - French
- `de` - German
- `zh-Hans` - Simplified Chinese
- `zh-Hant` - Traditional Chinese
- `ja` - Japanese
- `ko` - Korean

If the requested language is unavailable, API automatically returns first available language.

### Rate Limiting
- No official rate limits, but YouTube may block requests if too many are made quickly
- Recommended: Max 1 request per second per unique video ID
- Implement exponential backoff for retries

### CORS
API supports CORS for requests from:
- `chrome-extension://*` (Chrome extensions)
- `https://*.youtube.com` (YouTube domain)

### Subtitle Text Format
- Subtitle text may contain newline characters (`\n`) for multi-line subtitles
- Handle line breaks appropriately when displaying
- Unicode characters are fully supported (emojis, special characters, etc.)

### Timestamps
- `time` and `duration` are in seconds as floating-point numbers
- Start time is relative to video beginning
- Duration is how long the subtitle is displayed
- Times can have decimal precision (e.g., 1.36 seconds)

---

## 🔄 Integration Checklist for Chrome Extension

- [ ] Replace API base URL with `https://web-production-bd8bb.up.railway.app`
- [ ] Extract 11-character video ID from YouTube URL (remove `&t=...` params)
- [ ] Send POST request to `/api/subtitles` with correct JSON payload
- [ ] Handle different response status codes (200, 400, 403, 404, 500)
- [ ] Parse `subtitles` array from response
- [ ] Display subtitles with `time`, `duration`, and `text` fields
- [ ] Implement retry logic for network failures (3 attempts recommended)
- [ ] Add timeout for requests (30 seconds recommended)
- [ ] Handle edge cases (no subtitles, different languages, etc.)

---

## 📞 Support

For issues or questions about the API:
- Check GitHub repository for known issues
- Verify video has available subtitles
- Test endpoint with cURL or Postman first
- Check server health at `/api/health` endpoint

---

## 🔐 Security Notes

- No API key required (public API)
- Video IDs are validated (must be 11 characters)
- No authentication needed
- All requests are stateless
- HTTPS only (no HTTP)

---

## 📊 API Status

**Last Updated:** November 14, 2025

**Server Status:** ✅ Active and responding

**Deployment:** Railway

**Database:** N/A (Real-time fetching from YouTube)

