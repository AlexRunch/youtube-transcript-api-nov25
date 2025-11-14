# GET /api/subtitles API Endpoint Documentation

## 📋 Обзор

Новый **GET эндпоинт** специально создан для второго расширения (YouTube Description Generator + Title & Chapters).

**URL**: `GET /api/subtitles/<videoId>?lang=<language>`

## 🔗 API Endpoint

```
https://web-production-bd8bb.up.railway.app/api/subtitles/<videoId>?lang=<language>
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `videoId` | string | ✅ Yes | - | YouTube video ID (11 characters) |
| `lang` | string | ✅ Yes | - | Language code (ISO 639-1: `en`, `ru`, `de`, etc.) |
| `format` | string | ❌ No | `json` | Response format (`json` only for now) |

## 📤 Response Format

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
    },
    // ... more subtitles
  ]
}
```

### ❌ Error Response (HTTP 200 with success: false)

```json
{
  "success": false,
  "status": "error",
  "error": "No subtitles found for this video",
  "videoId": "dQw4w9WgXcQ",
  "language": "en",
  "count": 0,
  "subtitles": []
}
```

### ❌ Bad Request (HTTP 400)

```json
{
  "success": false,
  "status": "error",
  "error": "Invalid video ID format. Must be 11 characters.",
  "videoId": "invalid"
}
```

## 📊 Subtitle Object Fields

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `index` | number | ✅ | Sequential number (0-indexed) | `0`, `1`, `42` |
| `start` | number | ✅ | Start time in seconds (float) | `0.5`, `3.04`, `125.4` |
| `end` | number | ✅ | End time in seconds (float) | `3.2`, `5.72`, `128.1` |
| `dur` | number | ✅ | Duration in seconds (`end - start`) | `2.7`, `2.68`, `2.7` |
| `text` | string | ✅ | Subtitle text (plain text only) | `"Hello world"` |

### Important Notes

- `index` always starts from 0 and increments by 1
- `start`, `end`, `dur` are always **numbers** (float), never strings
- `end = start + dur` (mathematically guaranteed)
- `text` contains **plain text only** (no HTML, no XML entities)
- All fields are required for each subtitle

## 🚀 Usage Examples

### JavaScript/Fetch

```javascript
async function getSubtitles(videoId, language = 'en') {
  const url = `https://web-production-bd8bb.up.railway.app/api/subtitles/${videoId}?lang=${language}`;

  const response = await fetch(url);
  const data = await response.json();

  if (!data.success) {
    throw new Error(data.error);
  }

  return data.subtitles;
}

// Usage
getSubtitles('dQw4w9WgXcQ', 'en')
  .then(subtitles => {
    console.log(`Got ${subtitles.length} subtitles`);
    console.log(subtitles[0]);
  })
  .catch(error => console.error('Error:', error));
```

### cURL

```bash
# Get English subtitles
curl "https://web-production-bd8bb.up.railway.app/api/subtitles/dQw4w9WgXcQ?lang=en"

# Pretty print JSON
curl "https://web-production-bd8bb.up.railway.app/api/subtitles/dQw4w9WgXcQ?lang=en" | jq .

# Extract just the subtitles array
curl "https://web-production-bd8bb.up.railway.app/api/subtitles/dQw4w9WgXcQ?lang=en" | jq '.subtitles'

# Get first subtitle
curl "https://web-production-bd8bb.up.railway.app/api/subtitles/dQw4w9WgXcQ?lang=en" | jq '.subtitles[0]'
```

### Python

```python
import requests

def get_subtitles(video_id, language='en'):
    url = f'https://web-production-bd8bb.up.railway.app/api/subtitles/{video_id}?lang={language}'
    response = requests.get(url)
    data = response.json()

    if not data['success']:
        raise Exception(data['error'])

    return data['subtitles']

# Usage
subtitles = get_subtitles('dQw4w9WgXcQ', 'en')
print(f"Got {len(subtitles)} subtitles")
for subtitle in subtitles[:3]:
    print(f"[{subtitle['start']:.2f}-{subtitle['end']:.2f}] {subtitle['text']}")
```

## 🌐 Supported Languages

The API supports any language available through YouTube-Transcript-API:

**Common languages:**
- `en` — English
- `ru` — Russian (Русский)
- `uk` — Ukrainian (Українська)
- `de` — German (Deutsch)
- `fr` — French (Français)
- `es` — Spanish (Español)
- `it` — Italian (Italiano)
- `ja` — Japanese (日本語)
- `zh` — Chinese Simplified (简体中文)
- `pt` — Portuguese (Português)
- `pl` — Polish (Polski)
- `tr` — Turkish (Türkçe)

And **many more** (100+ languages supported).

## ⚙️ Behavior

### ✅ Requested Language Available
Returns subtitles in the requested language.

**Request:**
```
GET /api/subtitles/dQw4w9WgXcQ?lang=en
```

**Response:**
```json
{
  "success": true,
  "language": "en",
  "count": 61,
  "subtitles": [...]
}
```

### ✅ Requested Language Not Available - Fallback
Returns subtitles in the first available language.

**Request:**
```
GET /api/subtitles/CjTDBfxbEdc?lang=en
```

If English not available but Russian is:

**Response:**
```json
{
  "success": true,
  "language": "ru",
  "count": 341,
  "subtitles": [...]
}
```

### ❌ No Subtitles Available
Returns error response with empty subtitles array.

**Response:**
```json
{
  "success": false,
  "status": "error",
  "error": "No subtitles found for this video",
  "subtitles": []
}
```

### ❌ Video Not Found
Returns 404 error.

**Response:**
```json
{
  "success": false,
  "status": "error",
  "error": "Video not found on YouTube",
  "videoId": "invalid"
}
```

## 📝 Differences from POST Endpoint

| Feature | POST `/api/subtitles` | GET `/api/subtitles/<id>` |
|---------|---------------------|-------------------------|
| **HTTP Method** | POST | GET |
| **Parameters** | JSON body | Query string |
| **Video ID** | In body | In URL path |
| **Language** | In body | In query string `?lang=` |
| **Subtitle Fields** | `time`, `duration` | `index`, `start`, `end`, `dur` |
| **Use Case** | First extension | Second extension |

## 🔍 Validation & Error Codes

### HTTP 400 - Bad Request

**Invalid Video ID:**
```bash
curl "https://web-production-bd8bb.up.railway.app/api/subtitles/invalid?lang=en"
```

Response:
```json
{
  "success": false,
  "status": "error",
  "error": "Invalid video ID format. Must be 11 characters."
}
```

**Missing Language Parameter:**
```bash
curl "https://web-production-bd8bb.up.railway.app/api/subtitles/dQw4w9WgXcQ"
```

Response:
```json
{
  "success": false,
  "status": "error",
  "error": "Missing required parameter: lang"
}
```

### HTTP 404 - Not Found

**Video Not Found on YouTube:**
```json
{
  "success": false,
  "status": "error",
  "error": "Video not found on YouTube"
}
```

### HTTP 200 - Success or "No Subtitles"

All subtitle-related responses return HTTP 200, including:
- Successful subtitle retrieval
- Video found but no subtitles available
- Transcripts disabled
- Language not available (with fallback)

## ⏱️ Performance

- **Typical response time:** 2-5 seconds
- **For long videos (1000+ subtitles):** 5-10 seconds
- **Timeout:** 60 seconds (client-side)

## 🔒 CORS & Security

- ✅ Works with Chrome extensions (`chrome-extension://` origins)
- ✅ Works with YouTube domains
- ✅ No authentication required
- ✅ No API key required
- ✅ Subtitles are never logged or stored

## 📌 Testing Checklist

- [ ] Video ID validation (11 chars)
- [ ] Language parameter validation
- [ ] English subtitles retrieval
- [ ] Fallback to available language
- [ ] Subtitle structure (index, start, end, dur, text)
- [ ] Empty subtitles error handling
- [ ] Missing video error handling
- [ ] Multiple languages (en, ru, de, fr, etc.)
- [ ] Long videos (100+ subtitles)
- [ ] Response time < 10 seconds

## 📚 Related Documentation

- [POST /api/subtitles Documentation](./EXTENSION_INTEGRATION.md)
- [API Specification](./API_SPECIFICATION.md)
- [youtube-transcript-api Library](https://github.com/jdepoix/youtube-transcript-api)

## 🚀 Deployment Notes

- Deployed on Railway platform
- Listens on `0.0.0.0:5000` (locally) or Railway-assigned port
- Supports hot reload for development
- Production-ready error handling

---

**Last Updated:** 2025-11-14
**API Version:** 2.0 (with GET endpoint)
