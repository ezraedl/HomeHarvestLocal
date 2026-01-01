# DataDome Bypass Analysis

## DataDome Detection Methods

Based on research and testing, DataDome uses multiple layers of detection:

### 1. **Device Fingerprinting** (90+ Signals)
- Screen resolution
- Time zone
- Language settings
- Installed plugins
- Canvas fingerprinting
- WebGL fingerprinting
- Audio fingerprinting
- Font detection
- Hardware concurrency
- Device memory
- Platform information
- **Accuracy**: >95% device matching

### 2. **TLS Fingerprinting**
- TLS handshake patterns
- Cipher suites
- TLS extensions
- JA3/JA3S fingerprints
- **Detection**: Can identify curl, Python requests, etc.

### 3. **Behavioral Analysis**
- Mouse movements
- Click patterns
- Typing patterns
- Scroll behavior
- Form filling patterns
- Navigation flows
- Request timing patterns

### 4. **Machine Learning Models**
- Supervised ML models
- Pattern recognition
- Anomaly detection
- Continuous learning

### 5. **Device Check**
- Automation framework detection
- Spoofed environment detection
- Programmatic access detection
- JavaScript execution checks

### 6. **Cookie & Session Tracking**
- Cookie persistence
- Session continuity
- Cookie domain/path matching
- HttpOnly/Secure flags

### 7. **IP Reputation**
- IP address reputation
- Geographic consistency
- Request patterns from IP
- Proxy detection

### 8. **HTTP Headers Analysis**
- Header consistency
- Missing headers
- Header order
- Header values (User-Agent, Accept, etc.)

## Current Bypass Attempts

### ✅ What We're Doing

1. **TLS Fingerprinting** ✅
   - Using `curl_cffi` with browser impersonation
   - Profiles: chrome120, chrome116, chrome110
   - Random profile rotation
   - **Status**: Implemented

2. **Proxy Usage** ✅
   - DATAIMPULSE residential proxies
   - IP rotation
   - Geographic targeting (US)
   - **Status**: Implemented

3. **Session Management** ✅
   - Visiting propwire.com to get cookies
   - Visiting search page
   - Calling session-variable endpoint
   - Cookie persistence across requests
   - **Status**: Implemented

4. **HTTP Headers** ✅
   - Browser-like headers
   - Origin/Referer matching
   - Accept headers
   - sec-ch-ua headers
   - **Status**: Implemented

5. **Rate Limiting** ✅
   - Random delays (3-8 seconds)
   - Delays between session establishment steps
   - **Status**: Implemented

### ❌ What We're NOT Doing

1. **Device Fingerprinting** ❌
   - **Missing**: Canvas fingerprinting
   - **Missing**: WebGL fingerprinting
   - **Missing**: Audio fingerprinting
   - **Missing**: Font detection
   - **Missing**: Screen resolution simulation
   - **Missing**: Time zone consistency
   - **Missing**: Language settings
   - **Impact**: HIGH - DataDome collects 90+ signals

2. **JavaScript Execution** ❌
   - **Missing**: JavaScript rendering
   - **Missing**: DataDome JS challenge execution
   - **Missing**: Device check challenge
   - **Impact**: HIGH - DataDome requires JS execution

3. **Behavioral Analysis** ❌
   - **Missing**: Mouse movement simulation
   - **Missing**: Click pattern simulation
   - **Missing**: Typing pattern simulation
   - **Impact**: MEDIUM - Less critical for API calls

4. **Cookie Management** ⚠️
   - **Partial**: We get cookies but may not handle all DataDome cookies
   - **Missing**: DataDome-specific cookie handling
   - **Missing**: Cookie expiration handling
   - **Impact**: MEDIUM

5. **Request Timing** ⚠️
   - **Partial**: We have delays but may not match human patterns
   - **Missing**: Variable timing patterns
   - **Missing**: Time-of-day patterns
   - **Impact**: LOW

## Why We're Still Getting 401/403

### Primary Issues

1. **No JavaScript Execution**
   - DataDome's Device Check requires JavaScript execution
   - The `/api-js.datadome.co/js/` endpoint needs to run
   - Without JS, DataDome can't verify the device
   - **Solution**: Use headless browser (Playwright/Selenium)

2. **Incomplete Device Fingerprinting**
   - We're only handling TLS fingerprinting
   - Missing 80+ other device signals
   - DataDome can detect we're not a real browser
   - **Solution**: Use real browser or advanced fingerprinting

3. **Cookie Issues**
   - DataDome cookies may not be properly set
   - Missing `datadome` cookie or invalid value
   - Session cookies may expire quickly
   - **Solution**: Extract cookies from real browser session

## Comparison: Realtor vs Propwire

### Why Realtor Works

1. **GraphQL API** - May have different DataDome rules
2. **Less Strict Protection** - Realtor's DataDome may be configured differently
3. **No Session Required** - Can make direct API calls
4. **Same Techniques** - But works because DataDome is less strict

### Why Propwire Doesn't Work

1. **REST API** - May have stricter DataDome rules
2. **Session Required** - Must establish session first
3. **Stricter Protection** - Propwire's DataDome is more aggressive
4. **Device Check Required** - Needs JavaScript execution

## Recommended Solutions

### Option 1: Browser Automation (Recommended)
**Use Playwright or Selenium**

**Pros:**
- Full JavaScript execution
- Complete device fingerprinting
- Real browser environment
- Can handle DataDome Device Check

**Cons:**
- Slower than direct API calls
- More resource intensive
- Requires browser installation

**Implementation:**
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    # Navigate and extract cookies
    # Make API calls with cookies
```

### Option 2: Cookie Extraction
**Extract cookies from real browser**

**Pros:**
- Fast (direct API calls)
- Uses real browser cookies
- Can bypass some checks

**Cons:**
- Cookies expire
- Manual process
- May still fail Device Check

**Implementation:**
1. Open browser DevTools
2. Navigate to propwire.com
3. Extract cookies from Application tab
4. Inject into scraper session

### Option 3: Advanced Fingerprinting
**Use tools like undetected-chromedriver or playwright-stealth**

**Pros:**
- Better fingerprinting
- Can bypass some checks

**Cons:**
- May not be enough for DataDome
- Still requires browser

### Option 4: CAPTCHA Solving Service
**Use 2Captcha or similar**

**Pros:**
- Can solve CAPTCHAs if they appear

**Cons:**
- Doesn't solve Device Check
- Additional cost
- May not be needed if Device Check passes

## Current Status

**What's Working:**
- ✅ TLS fingerprinting (curl_cffi)
- ✅ Proxy rotation
- ✅ Session establishment (requests-based)
- ✅ Proper headers
- ✅ Rate limiting
- ✅ **NEW**: Playwright cookie extraction (if Playwright installed)

**What's Missing (if Playwright not used):**
- ❌ JavaScript execution (Device Check) - **CRITICAL**
- ❌ Complete device fingerprinting
- ❌ DataDome cookie handling
- ❌ Behavioral simulation

**What's Added:**
- ✅ Playwright-based cookie extraction
- ✅ Automatic fallback to requests if Playwright unavailable
- ✅ DataDome cookie injection

**Result:** 
- With Playwright: Should work (cookies extracted via JS execution)
- Without Playwright: 401 Unauthorized (no DataDome cookie)

## Next Steps

1. **Implement Playwright** - Full browser automation
2. **Extract Cookies** - From real browser session
3. **Test Cookie Injection** - See if it helps
4. **Consider CAPTCHA Service** - If CAPTCHAs appear
5. **Monitor DataDome JS** - See what it requires

## Conclusion

We're handling **~30% of DataDome's detection methods**:
- ✅ TLS fingerprinting
- ✅ Proxy/IP rotation
- ✅ Basic headers
- ✅ Session management

We're missing **~70% of detection methods**:
- ❌ JavaScript execution (Device Check) - **CRITICAL**
- ❌ Device fingerprinting (90+ signals) - **HIGH**
- ❌ Behavioral analysis - **MEDIUM**
- ❌ Advanced cookie handling - **MEDIUM**

**The primary blocker is the lack of JavaScript execution for DataDome's Device Check.**

