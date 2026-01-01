# Propwire Scraper Troubleshooting

## Current Status

✅ **Playwright Working**: Successfully extracting DataDome cookies
✅ **Cookie Caching**: Cookies are being cached in memory
❌ **API Calls Still Failing**: Getting 401/403 errors even with fresh cookies

## Issue Analysis

### What's Working

1. **Playwright Cookie Extraction**: ✅
   - Successfully extracting DataDome cookies (length: 128)
   - Cookies are being cached
   - Playwright is using proxy correctly

2. **Cookie Caching**: ✅
   - Cookies cached in memory
   - Cache TTL: 12 hours
   - Automatic refresh on 401/403 errors

### What's Not Working

1. **API Calls**: ❌
   - Still getting 401 Unauthorized
   - Still getting 403 Forbidden
   - Even with fresh cookies extracted via Playwright

## Possible Causes

### 1. Cookie/Proxy Mismatch

**Issue**: Cookies extracted with one proxy IP, but API calls use different proxy IP.

**Evidence**:
- Playwright extracts cookies with proxy A
- API calls use proxy B (rotated proxy)
- DataDome sees different IPs → blocks

**Solution**: Use same proxy for both Playwright and API calls, OR extract cookies without proxy and use proxy only for API calls.

### 2. Cookie Session Binding

**Issue**: DataDome cookies might be bound to the browser session/fingerprint, not just the IP.

**Evidence**:
- Cookies extracted successfully
- But invalid when used with requests/curl_cffi
- Different TLS fingerprint between Playwright and curl_cffi

**Solution**: 
- Use Playwright for ALL requests (not just cookie extraction)
- OR ensure TLS fingerprint matches between Playwright and curl_cffi

### 3. DataDome Advanced Detection

**Issue**: DataDome might be detecting:
- Request pattern (too fast, too regular)
- Missing browser headers
- Different user-agent between cookie extraction and API calls
- Missing JavaScript execution for API calls

**Solution**: 
- Use Playwright for all requests
- Add more delays
- Match headers exactly

### 4. Cookie Domain/Path Issues

**Issue**: Cookies might not be set correctly for `api.propwire.com`.

**Evidence**:
- Cookies extracted from `propwire.com`
- But API calls go to `api.propwire.com`
- Domain mismatch?

**Solution**: Verify cookie domains are set correctly.

## Recommended Solutions

### Solution 1: Use Same Proxy for Playwright and API Calls

**Current**: Playwright uses proxy, but API calls might use different proxy.

**Fix**: Ensure same proxy is used for both.

```python
# In _get_datadome_cookies_playwright
# Already using self.proxy - good!

# In _rest_post
# Already using self.proxies - good!

# But check if proxy is being rotated between calls
```

### Solution 2: Use Playwright for All Requests

**Current**: Playwright only for cookie extraction, requests/curl_cffi for API calls.

**Fix**: Use Playwright for all requests (slower but more reliable).

```python
def _rest_post_playwright(self, endpoint: str, payload: dict) -> dict:
    """Use Playwright for API calls instead of requests."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Set cookies
        for name, value in self.session.cookies.items():
            context.add_cookies([{
                'name': name,
                'value': value,
                'domain': '.propwire.com',
                'path': '/'
            }])
        
        # Make API call via fetch
        response = page.evaluate(f"""
            fetch('{endpoint}', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({json.dumps(payload)})
            }}).then(r => r.json())
        """)
        
        browser.close()
        return response
```

### Solution 3: Extract Cookies Without Proxy

**Current**: Playwright uses proxy, cookies might be tied to proxy IP.

**Fix**: Extract cookies without proxy, use proxy only for API calls.

```python
# In _get_datadome_cookies_playwright
# Don't use proxy for cookie extraction
launch_options = {
    'headless': True,
    # No proxy here
}

# Use proxy only for API calls
# In _rest_post
# Use proxy here
```

### Solution 4: Verify Cookie Injection

**Current**: Cookies might not be injected correctly.

**Fix**: Add logging to verify cookies are set.

```python
# After injecting cookies
logger.debug(f"Cookies in session: {list(self.session.cookies.keys())}")
logger.debug(f"DataDome cookie present: {'datadome' in [c.name for c in self.session.cookies]}")
```

## Testing Steps

1. **Test without proxy**:
   ```python
   scraper_input = ScraperInput(..., proxy=None)
   ```

2. **Test with same proxy**:
   ```python
   # Use same proxy for both Playwright and API calls
   # Don't rotate proxy
   ```

3. **Test cookie injection**:
   ```python
   # Log cookies before API call
   # Verify datadome cookie is present
   ```

4. **Test with Playwright for all requests**:
   ```python
   # Use Playwright for API calls too
   ```

## Next Steps

1. ✅ Verify Playwright is using same proxy as API calls
2. ✅ Add logging to verify cookie injection
3. ⚠️ Test without proxy to see if that's the issue
4. ⚠️ Consider using Playwright for all requests if needed

## Current Implementation Status

- ✅ Playwright cookie extraction: Working
- ✅ Cookie caching: Working
- ❌ API calls with cookies: Failing (401/403)
- ⚠️ Need to investigate cookie/proxy mismatch or session binding



