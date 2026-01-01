# Propwire.com API Discovery

## Investigation Date

2025-01-31

## Discovered API Endpoints

### 1. Autocomplete API

- **Endpoint**: `POST https://api.propwire.com/api/auto_complete`
- **Purpose**: Location/address autocomplete suggestions
- **Status**: ✅ Confirmed via network inspection
- **Notes**: Called when user types in search box

### 2. Session Management

- **Endpoint**: `POST https://propwire.com/session-variable`
- **Purpose**: Session variable management
- **Status**: ✅ Confirmed via network inspection

### 3. Search Page

- **Endpoint**: `GET https://propwire.com/search?filters={...}`
- **Purpose**: Main search page
- **Status**: ✅ Confirmed
- **Notes**: Uses query parameters for filters (JSON encoded)

### 4. Property Search API ⭐ **MAIN ENDPOINT**

- **Endpoint**: `POST https://api.propwire.com/api/property_search`
- **Purpose**: Main property search endpoint that returns property listings
- **Status**: ✅ **CONFIRMED** - Found via network inspection
- **Authentication**: **Unauthenticated** - Works without login
- **Notes**:
  - Called when location is selected or search is performed
  - Returns property listings with pagination
  - Tested with Dallas County, TX - returned 756,920 results
  - Request/response format needs to be captured

## Anti-Bot Protection

### DataDome

- **Service**: DataDome (confirmed)
- **Endpoint**: `POST https://api-js.datadome.co/js/`
- **Impact**: High - Active protection detected
- **Strategy**:
  - Use TLS fingerprinting (curl_cffi)
  - Rotate browser impersonation profiles
  - Use residential proxies
  - Implement conservative rate limiting (5-10 seconds)

## Technology Stack

- **Frontend**: React SPA (based on build assets)
- **Maps**: Mapbox (for map visualization)
- **Analytics**: Amplitude, New Relic
- **Payment**: Stripe
- **Third-party**: Facebook Pixel, Google Tag Manager

## API Structure (To Be Determined)

Based on the autocomplete endpoint pattern, Propwire likely uses:

- **Base URL**: `https://api.propwire.com/api/`
- **Format**: REST API (not GraphQL)
- **Authentication**: Likely session-based or API key (needs investigation)

## Confirmed Endpoints

### ✅ Property Search (MAIN)

- **`POST /api/property_search`** - ✅ **CONFIRMED** - Main property search endpoint
  - Works unauthenticated
  - Returns property listings with pagination
  - Tested successfully with Dallas County, TX search

## Potential Endpoints (To Verify)

- `/api/property/{id}` - Individual property details
- `/api/filters` - Available filters
- `/api/export` - Data export functionality

## Next Steps

1. **Intercept Property Search Requests**

   - Perform a search that returns results
   - Monitor network tab for property data API calls
   - Document request/response format

2. **Analyze Request Format**

   - Headers required
   - Authentication mechanism
   - Request body structure
   - Query parameters

3. **Document Response Format**

   - Property data structure
   - Field names and types
   - Pagination mechanism
   - Error responses

4. **Test Authentication**
   - Determine if login required
   - Check for API keys
   - Test session management

## References

- Existing scraper: https://github.com/pim97/propwire.com-scraper (reference only)
- DataDome protection: Confirmed active
- Terms of Service: https://propwire.com/terms-of-use
- Privacy Policy: https://propwire.com/privacy-policy

## Key Findings

### ✅ Property Search Works Unauthenticated

- **Confirmed**: Property search API works without authentication
- **Endpoint**: `POST https://api.propwire.com/api/property_search`
- **Test Result**: Successfully retrieved 756,920 properties for Dallas County, TX
- **Pagination**: Supports pagination (page 1 of 3028 shown)

### 🔍 DataDome Bypass Strategy (Compared to Realtor)

**How Realtor Bypasses DataDome:**

1. **No session establishment** - Makes GraphQL requests directly using base session
2. **curl_cffi with TLS fingerprinting** - Browser impersonation (chrome120, chrome119, etc.)
3. **Proxy support** - Uses proxy when provided (DATAIMPULSE)
4. **DEFAULT_HEADERS** - Simple, consistent headers
5. **Random delays** - 3-8 seconds between requests

**Propwire Differences:**

- **Requires session establishment** - Must visit propwire.com first to get cookies (401 without it)
- **Session-variable endpoint** - Must call `/session-variable` before API calls
- **More strict DataDome** - Even with curl_cffi + proxy, still getting 403/401
- **Same base approach** - Uses curl_cffi + proxy + proper headers (like Realtor)

**Current Status:**

- ✅ curl_cffi installed and configured
- ✅ DATAIMPULSE proxy configured
- ✅ Session establishment implemented
- ✅ Session-variable endpoint called
- ⚠️ Still getting 403/401 - DataDome is more strict than Realtor's

### Next Steps

1. **Capture Request/Response Format**

   - Document request body structure
   - Document response structure
   - Identify required headers
   - Map field names to Property model

2. **Test Pagination**

   - Verify pagination parameters
   - Test page size limits
   - Document pagination response format

3. **Test Filters**

   - Price range
   - Beds/Baths
   - Property types
   - Lead types
   - Date ranges

4. **Property Details**
   - Find endpoint for individual property details
   - Document required parameters
