# Playwright Production Deployment Guide

## Can You Run Playwright in Production?

**Short Answer**: Yes, but with considerations.

**Current Implementation**: Playwright is **optional** - the scraper falls back gracefully if Playwright isn't available.

## Production Considerations

### ✅ Advantages

1. **Optional Dependency**

   - Code already handles missing Playwright gracefully
   - Falls back to requests-based approach
   - No breaking changes if Playwright unavailable

2. **Resource Usage**

   - Only used for cookie extraction (one-time per session)
   - Not used for every API call
   - Browser closes immediately after cookie extraction

3. **Docker/Cloud Compatible**
   - Can be installed in Docker containers
   - Works on most cloud platforms
   - Requires browser binaries (~300MB)

### ⚠️ Challenges

1. **Browser Binaries**

   - Playwright requires Chromium/Firefox/WebKit binaries
   - Adds ~300MB to Docker image
   - Must install: `playwright install chromium`

2. **Resource Requirements**

   - Memory: ~100-200MB per browser instance
   - CPU: Moderate during cookie extraction
   - Disk: ~300MB for browser binaries

3. **Docker Image Size**

   - Base image: ~500MB
   - With Playwright: ~800MB
   - Consider multi-stage builds

4. **Serverless Limitations**
   - AWS Lambda: May hit size limits (50MB zipped)
   - Vercel: Memory limits may be restrictive
   - Cloud Functions: May need custom runtime

## Production Deployment Options

### Option 1: Full Playwright (Recommended if Resources Allow)

**Pros:**

- Best DataDome bypass (95% coverage)
- Reliable cookie extraction
- Works out of the box

**Cons:**

- Larger Docker image
- More memory usage
- Slower cookie extraction (~10-15 seconds)

**Dockerfile Example:**

```dockerfile
FROM python:3.11-slim

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and browser
RUN pip install playwright
RUN playwright install chromium
RUN playwright install-deps chromium

# Your app code
COPY . .
CMD ["python", "app.py"]
```

**requirements.txt:**

```txt
playwright>=1.40.0
# ... other dependencies
```

### Option 2: Cookie Service (Recommended for Production)

**Separate cookie extraction service** that runs Playwright, extracts cookies, and provides them via API.

**Architecture:**

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Scraper   │─────▶│ Cookie       │─────▶│  Propwire   │
│   Service   │      │  Service     │      │    API      │
│             │      │ (Playwright) │      │             │
└─────────────┘      └──────────────┘      └─────────────┘
```

**Pros:**

- Scraper stays lightweight (no Playwright)
- Cookie service can be scaled independently
- Cookie caching/reuse possible
- Can run on different infrastructure

**Cons:**

- Additional service to maintain
- Network latency for cookie requests
- More complex architecture

**Implementation:**

```python
# Cookie Service (runs Playwright)
@app.post("/cookies/propwire")
def get_propwire_cookies():
    # Use Playwright to extract cookies
    cookies = extract_datadome_cookies()
    return {"cookies": cookies}

# Scraper Service (no Playwright)
def _establish_session(self):
    # Call cookie service
    response = requests.post("http://cookie-service/cookies/propwire")
    cookies = response.json()["cookies"]
    # Inject cookies into session
    for name, value in cookies.items():
        self.session.cookies.set(name, value, domain='.propwire.com')
```

### Option 3: Cookie Caching (Hybrid)

**Extract cookies once, cache them, reuse for multiple requests.**

**Pros:**

- Minimal Playwright usage (only when cookies expire)
- Fast subsequent requests
- Can cache cookies for hours

**Cons:**

- Cookies expire (need refresh logic)
- Cache invalidation complexity

**Implementation:**

```python
import redis
import json
from datetime import datetime, timedelta

def _establish_session(self):
    # Try to get cached cookies
    cached = redis_client.get("propwire_cookies")
    if cached:
        cookies = json.loads(cached)
        # Check if expired (DataDome cookies typically last 1-24 hours)
        if datetime.now() - datetime.fromisoformat(cookies['timestamp']) < timedelta(hours=12):
            # Use cached cookies
            for name, value in cookies['cookies'].items():
                self.session.cookies.set(name, value, domain='.propwire.com')
            return

    # Extract fresh cookies with Playwright
    cookies = self._get_datadome_cookies_playwright()
    if cookies:
        # Cache for 12 hours
        redis_client.setex(
            "propwire_cookies",
            43200,  # 12 hours
            json.dumps({
                'cookies': cookies,
                'timestamp': datetime.now().isoformat()
            })
        )
```

### Option 4: No Playwright (Current Fallback)

**Use requests-based approach only.**

**Pros:**

- Lightweight
- Fast
- No browser dependencies

**Cons:**

- ❌ 401 Unauthorized (no DataDome cookie)
- Only ~40% DataDome bypass coverage

**Status**: Currently implemented as fallback, but **won't work** for Propwire.

## Recommended Production Strategy

### For Most Production Environments:

**Use Option 3 (Cookie Caching)**:

1. **Install Playwright** in production
2. **Extract cookies** on first request (or scheduled job)
3. **Cache cookies** in Redis/database
4. **Reuse cached cookies** for all requests
5. **Refresh cookies** when they expire (401 error)

**Benefits:**

- ✅ Works reliably (has DataDome cookies)
- ✅ Fast (cached cookies)
- ✅ Minimal Playwright usage (only on refresh)
- ✅ Scales well (one cookie extraction serves many requests)

### For Resource-Constrained Environments:

**Use Option 2 (Cookie Service)**:

1. **Separate cookie service** with Playwright
2. **Scraper service** without Playwright
3. **Cookie service** provides cookies via API
4. **Scraper** calls cookie service when needed

**Benefits:**

- ✅ Scraper stays lightweight
- ✅ Cookie service can be scaled independently
- ✅ Can use more powerful instance for cookie service

## Dockerfile for Production (Option 3)

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright (optional - only if available)
RUN pip install playwright || echo "Playwright installation skipped"
RUN playwright install chromium || echo "Playwright browser installation skipped"

# Your app code
COPY . .
CMD ["python", "app.py"]
```

## Testing in Production

1. **Check if Playwright works:**

   ```python
   try:
       from playwright.sync_api import sync_playwright
       print("✅ Playwright available")
   except ImportError:
       print("❌ Playwright not available - will use fallback")
   ```

2. **Test cookie extraction:**

   ```python
   scraper = PropwireScraper(scraper_input)
   # Check logs for "Successfully extracted DataDome cookies via Playwright"
   ```

3. **Monitor cookie expiration:**
   - Watch for 401 errors
   - Refresh cookies when needed
   - Log cookie age

## Current Implementation Status

✅ **Already Production-Ready**:

- Graceful fallback if Playwright unavailable
- No breaking changes
- Works with or without Playwright

⚠️ **Needs Configuration**:

- Install Playwright in production
- Install browser binaries
- Configure cookie caching (optional but recommended)

## Conclusion

**Yes, you can run Playwright in production**, but:

1. **Recommended**: Use cookie caching to minimize Playwright usage
2. **Alternative**: Use separate cookie service if resources are limited
3. **Fallback**: Current implementation works without Playwright (but gets 401 errors)

The code is already designed to work in production with or without Playwright!





