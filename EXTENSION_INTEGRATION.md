# Chrome Extension Integration Guide

## 🚀 Quick Start

### API Endpoint
```
https://web-production-bd8bb.up.railway.app/api/subtitles
```

### Minimal Example
```javascript
async function getSubtitles(videoUrl) {
  // Extract video ID from URL
  const videoId = new URL(videoUrl).searchParams.get('v');

  if (!videoId || videoId.length !== 11) {
    throw new Error('Invalid video ID');
  }

  // Call API
  const response = await fetch('https://web-production-bd8bb.up.railway.app/api/subtitles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      videoId: videoId,
      language: 'en',
      translateTo: null
    })
  });

  if (!response.ok) throw new Error('API request failed');

  const data = await response.json();

  if (!data.success) {
    throw new Error(data.error);
  }

  return data.subtitles;
}

// Usage
getSubtitles('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
  .then(subtitles => console.log(subtitles))
  .catch(error => console.error(error));
```

---

## 📋 Response Format

Each subtitle object contains:
```javascript
{
  "time": 1.36,        // Start time in seconds
  "duration": 1.68,    // Duration in seconds
  "text": "[♪♪♪]"      // Subtitle text (may contain \n)
}
```

Full response:
```javascript
{
  "success": true,
  "videoId": "dQw4w9WgXcQ",
  "language": "en",
  "subtitles": [
    { "time": 1.36, "duration": 1.68, "text": "[♪♪♪]" },
    { "time": 18.64, "duration": 3.24, "text": "♪ We're no strangers to love ♪" },
    // ... more subtitles
  ],
  "count": 61
}
```

---

## 🎯 Implementation Recommendations

### 1. Video ID Extraction
```javascript
function extractVideoId(url) {
  try {
    const urlObj = new URL(url);
    const videoId = urlObj.searchParams.get('v');

    if (!videoId || videoId.length !== 11) {
      return null;
    }

    return videoId;
  } catch (e) {
    return null;
  }
}
```

### 2. Error Handling
```javascript
async function getSubtitlesWithErrorHandling(videoId) {
  try {
    const response = await fetch(
      'https://web-production-bd8bb.up.railway.app/api/subtitles',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          videoId: videoId,
          language: 'en',
          translateTo: null
        }),
        timeout: 30000  // 30 second timeout
      }
    );

    const data = await response.json();

    if (!data.success) {
      // Handle specific errors
      if (data.error.includes('disabled')) {
        throw new Error('This video has subtitles disabled');
      } else if (data.error.includes('unavailable')) {
        throw new Error('This video is not available');
      } else {
        throw new Error(data.error);
      }
    }

    return data.subtitles;
  } catch (error) {
    console.error('Failed to fetch subtitles:', error);
    throw error;
  }
}
```

### 3. Retry Logic
```javascript
async function getSubtitlesWithRetry(videoId, maxRetries = 3) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await getSubtitlesWithErrorHandling(videoId);
    } catch (error) {
      if (attempt === maxRetries) {
        throw error;  // Last attempt failed
      }

      // Wait before retrying (exponential backoff)
      const delay = Math.pow(2, attempt - 1) * 1000;  // 1s, 2s, 4s
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}
```

### 4. Subtitle Display
```javascript
function formatSubtitle(subtitle) {
  return {
    startTime: subtitle.time,
    endTime: subtitle.time + subtitle.duration,
    text: subtitle.text
      .replace(/\\n/g, ' ')  // Convert newlines to spaces
      .trim()
  };
}

function displaySubtitles(subtitles) {
  const formatted = subtitles.map(formatSubtitle);

  // Sort by time (should already be sorted)
  formatted.sort((a, b) => a.startTime - b.startTime);

  return formatted;
}
```

### 5. Language Selection
```javascript
// Try to get subtitles in preferred language, fallback to available language
async function getSubtitlesInPreferredLanguage(videoId, preferredLang = 'en') {
  const response = await fetch(
    'https://web-production-bd8bb.up.railway.app/api/subtitles',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        videoId: videoId,
        language: preferredLang,
        translateTo: null
      })
    }
  );

  const data = await response.json();

  if (data.success) {
    console.log(`Got subtitles in ${data.language}`);
    if (data.language !== preferredLang) {
      console.warn(`Requested ${preferredLang}, got ${data.language}`);
    }
    return data.subtitles;
  } else {
    throw new Error(data.error);
  }
}
```

---

## 📱 Content Script Example

For use in `content.js`:

```javascript
// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getSubtitles') {
    const videoId = extractVideoId(window.location.href);

    if (!videoId) {
      sendResponse({ success: false, error: 'Invalid video ID' });
      return;
    }

    getSubtitlesWithRetry(videoId)
      .then(subtitles => {
        sendResponse({ success: true, subtitles: subtitles });
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });

    // Required for async response
    return true;
  }
});
```

---

## 🔌 Popup Script Example

For use in `popup.js`:

```javascript
document.getElementById('getSubtitles').addEventListener('click', () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    chrome.tabs.sendMessage(tabs[0].id, { action: 'getSubtitles' }, (response) => {
      if (response.success) {
        displaySubtitles(response.subtitles);
      } else {
        showError(response.error);
      }
    });
  });
});
```

---

## ✅ Testing Checklist

- [ ] Extract video ID correctly from various URL formats
- [ ] Handle missing video ID gracefully
- [ ] Display first subtitle immediately
- [ ] Show loading state while fetching
- [ ] Handle network errors with retry logic
- [ ] Display clear error message if subtitles unavailable
- [ ] Support different languages (test with non-English subtitles)
- [ ] Handle videos with newlines in subtitle text
- [ ] Test with long videos (1000+ subtitles)
- [ ] Test with videos without subtitles
- [ ] Verify response times (should be < 5 seconds typically)

---

## 🐛 Known Issues & Limitations

1. **Language Detection** - API doesn't list available languages upfront. You must request `/api/subtitles` to find out if language is available.

2. **Translation** - Translation parameter currently not implemented. Use the subtitle text as-is.

3. **Auto-generated Captions** - Returns whichever subtitles are available (auto-generated or manual).

4. **YouTube Blocking** - Railway IP may be blocked by YouTube if too many requests. In that case, server owner will need to configure Webshare proxy (see main README).

---

## 📊 Performance Tips

- Cache subtitles locally (use Chrome storage API)
- Don't re-fetch subtitles on page reload if already cached
- Show spinner while loading
- Implement request timeout (30 seconds)
- Batch subtitle processing if handling 1000+ items

---

## 🔒 Privacy & Security

- API doesn't log or store video IDs or subtitles
- All requests go directly to YouTube via API server
- No authentication needed
- Safe to use from public Chrome extensions

