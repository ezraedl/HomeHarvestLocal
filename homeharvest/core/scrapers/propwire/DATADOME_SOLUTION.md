# DataDome Bypass Solution

## Key Finding

**DataDome requires JavaScript execution** to:
1. Load `https://js.datadome.co/tags.js`
2. Run Device Check
3. Set `datadome` cookie with token
4. Collect device fingerprinting data

**Current Issue**: We're using `requests` + `curl_cffi` which doesn't execute JavaScript.

## Solution: Hybrid Approach

### Strategy 1: Cookie Extraction + Direct API (Fast)

1. Use Playwright to establish session and get cookies
2. Extract DataDome cookies
3. Use cookies with `requests` for API calls

**Pros:**
- Fast (direct API calls after cookie extraction)
- Full JavaScript execution for cookie generation
- Can reuse cookies for multiple requests

**Cons:**
- Cookies expire (need to refresh periodically)
- Still need Playwright for initial setup

### Strategy 2: Full Playwright (Reliable)

1. Use Playwright for all operations
2. Let browser handle DataDome automatically
3. Extract data from API responses

**Pros:**
- Most reliable
- Handles all DataDome checks automatically
- Can handle CAPTCHAs if they appear

**Cons:**
- Slower than direct API calls
- More resource intensive

## Implementation Plan

### Phase 1: Cookie Extraction (Recommended First Step)

```python
from playwright.sync_api import sync_playwright
import requests

def get_datadome_cookies():
    """Extract DataDome cookies from browser session."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1200},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            locale='en-US',
            timezone_id='America/New_York',
        )
        page = context.new_page()
        
        # Navigate to propwire.com
        page.goto('https://propwire.com/', wait_until='networkidle')
        time.sleep(5)  # Wait for DataDome JS to execute
        
        # Navigate to search page
        page.goto('https://propwire.com/search', wait_until='networkidle')
        time.sleep(3)
        
        # Extract cookies
        cookies = context.cookies()
        browser.close()
        
        # Convert to requests format
        cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
        return cookie_dict
```

### Phase 2: Use Cookies with Requests

```python
# After getting cookies from Playwright
session = requests.Session()
for name, value in datadome_cookies.items():
    session.cookies.set(name, value, domain='.propwire.com')

# Now make API calls with cookies
response = session.post(
    'https://api.propwire.com/api/property_search',
    headers={...},
    json=payload
)
```

### Phase 3: Cookie Refresh

- Check if cookies are expired (401/403)
- Re-run cookie extraction
- Update session cookies

## What This Solves

### ✅ All Detection Methods Covered

1. **JavaScript Execution** ✅
   - Playwright executes DataDome JS
   - Device Check runs
   - Cookies are set properly

2. **Device Fingerprinting** ✅
   - Real browser environment
   - All 90+ signals available
   - Screen resolution, timezone, etc.

3. **TLS Fingerprinting** ✅
   - Playwright uses real browser TLS
   - Perfect fingerprint match

4. **Cookie Management** ✅
   - DataDome cookies properly set
   - Cookie persistence
   - Domain/path matching

5. **Behavioral Analysis** ✅
   - Real browser interactions
   - Natural navigation patterns

6. **IP Reputation** ✅
   - Use proxy with Playwright
   - Residential IPs

## Current Status vs Required

| Detection Method | Current | Required | Solution |
|-----------------|---------|----------|----------|
| TLS Fingerprinting | ✅ curl_cffi | ✅ Real Browser | Playwright |
| JavaScript Execution | ❌ None | ✅ Required | Playwright |
| Device Fingerprinting | ⚠️ Partial | ✅ Full | Playwright |
| Cookie Management | ⚠️ Basic | ✅ DataDome Cookies | Playwright |
| Behavioral Analysis | ❌ None | ⚠️ Optional | Playwright |
| IP Rotation | ✅ Proxy | ✅ Proxy | Keep Proxy |

## Recommended Implementation

1. **Start with Cookie Extraction** (Phase 1)
   - Fastest to implement
   - Can test immediately
   - If it works, we're done

2. **Fallback to Full Playwright** (Phase 2)
   - If cookies expire too quickly
   - If cookie extraction doesn't work
   - More reliable long-term

3. **Optimize** (Phase 3)
   - Cache cookies
   - Refresh only when needed
   - Batch requests

## Next Steps

1. Install Playwright: `pip install playwright && playwright install chromium`
2. Implement cookie extraction function
3. Test with extracted cookies
4. If successful, integrate into scraper
5. If not, implement full Playwright solution


