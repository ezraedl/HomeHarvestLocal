# Cookie Caching Implementation

## Overview

The Propwire scraper now includes **intelligent cookie caching** to minimize Playwright usage and improve performance in production.

## How It Works

### 1. Cookie Extraction Flow

```
┌─────────────────┐
│  Scraper Init   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│ Check Cached Cookies    │
│ (Redis or Memory)       │
└────────┬───────────────┘
         │
    ┌────┴────┐
    │ Found?  │
    └────┬────┘
         │
    ┌────┴────┐
    │         │
   Yes       No
    │         │
    │         ▼
    │    ┌──────────────────────┐
    │    │ Extract with         │
    │    │ Playwright           │
    │    └──────────┬───────────┘
    │               │
    │               ▼
    │    ┌──────────────────────┐
    │    │ Cache Cookies         │
    │    │ (Redis or Memory)     │
    │    └──────────┬───────────┘
    │               │
    └───────────────┘
         │
         ▼
┌─────────────────────────┐
│ Use Cookies for API     │
│ Requests                │
└─────────────────────────┘
```

### 2. Cache Layers

1. **Redis Cache** (if available)
   - Shared across all scraper instances
   - Persistent across restarts
   - TTL: 12 hours

2. **In-Memory Cache** (fallback)
   - Shared across instances in same process
   - Lost on restart
   - TTL: 12 hours

### 3. Automatic Refresh

- **On 401/403 errors**: Automatically refreshes cookies and retries
- **On cache expiration**: Automatically extracts fresh cookies
- **Force refresh**: Can be triggered manually with `force_refresh=True`

## Configuration

### Redis (Optional)

Set environment variable:
```bash
REDIS_URL=redis://localhost:6379/0
```

Or in Docker:
```yaml
environment:
  - REDIS_URL=redis://redis:6379/0
```

### Cookie TTL

Default: 12 hours (43200 seconds)

DataDome cookies typically last 12-24 hours, so 12 hours is a safe default.

## Benefits

### Performance
- ✅ **Fast**: Cached cookies used immediately (no Playwright delay)
- ✅ **Efficient**: Playwright only used when cookies expire
- ✅ **Scalable**: One cookie extraction serves many requests

### Reliability
- ✅ **Automatic refresh**: Handles cookie expiration gracefully
- ✅ **Error recovery**: Refreshes cookies on 401/403 errors
- ✅ **Fallback**: Works with or without Redis

### Production Ready
- ✅ **Optional Redis**: Works without Redis (uses in-memory cache)
- ✅ **Thread-safe**: Uses locks for in-memory cache
- ✅ **Logging**: Comprehensive logging for debugging

## Usage Examples

### Basic Usage (Automatic Caching)

```python
from homeharvest.core.scrapers import ScraperInput
from homeharvest.core.scrapers.propwire import PropwireScraper

scraper_input = ScraperInput(
    location="46201",
    listing_type=ListingType.FOR_SALE,
)

# First call: Extracts cookies with Playwright and caches them
scraper1 = PropwireScraper(scraper_input)
results1 = scraper1.search()

# Second call: Uses cached cookies (fast, no Playwright)
scraper2 = PropwireScraper(scraper_input)
results2 = scraper2.search()  # Uses cached cookies
```

### Force Refresh

```python
# Force refresh cookies (skip cache)
scraper._establish_session(force_refresh=True)
```

### Check Cache Status

```python
# Check if cookies are cached
cached = scraper._get_cached_cookies()
if cached:
    print("Cookies are cached")
else:
    print("No cached cookies, will extract fresh")
```

## Monitoring

### Log Messages

**Cache Hit:**
```
Using cached DataDome cookies from Redis (age: 0:15:30)
```

**Cache Miss:**
```
Extracting fresh DataDome cookies...
Successfully extracted DataDome cookies via Playwright
Cached DataDome cookies in Redis (TTL: 12 hours)
```

**Cookie Refresh:**
```
401 Unauthorized received, refreshing cookies and retrying...
403 Forbidden received, refreshing cookies and retrying...
```

### Metrics to Monitor

1. **Cache Hit Rate**: How often cached cookies are used
2. **Cookie Extraction Frequency**: How often Playwright is used
3. **401/403 Error Rate**: How often cookies expire
4. **Cookie Age**: Average age of cached cookies

## Troubleshooting

### Cookies Not Caching

1. **Check Redis connection:**
   ```python
   import redis
   r = redis.Redis(host='localhost', port=6379)
   r.ping()  # Should return True
   ```

2. **Check logs:**
   - Look for "Redis not available" messages
   - Check for cache write errors

### Cookies Expiring Too Fast

1. **Check cookie TTL:**
   - Default is 12 hours
   - DataDome cookies may expire sooner
   - Adjust `_COOKIE_CACHE_TTL` if needed

2. **Monitor 401 errors:**
   - High 401 rate = cookies expiring
   - May need to reduce TTL

### Playwright Still Used Frequently

1. **Check cache:**
   - Verify cookies are being cached
   - Check cache expiration times

2. **Check Redis:**
   - Verify Redis is working
   - Check Redis memory usage

## Production Recommendations

1. **Use Redis** for shared cache across instances
2. **Monitor cache hit rate** to optimize TTL
3. **Set up alerts** for high 401/403 error rates
4. **Schedule cookie refresh** before expiration (optional)

## Implementation Details

### Cache Key
- Default: `"propwire_datadome_cookies"`
- Can be customized per instance if needed

### Cache Structure
```json
{
  "cookies": {
    "datadome": "...",
    "XSRF-TOKEN": "...",
    ...
  },
  "timestamp": "2025-01-31T12:00:00"
}
```

### Thread Safety
- Redis: Thread-safe by design
- In-memory: Uses `threading.Lock()` for safety

## Future Enhancements

1. **Cookie validation**: Check if cookies are still valid before using
2. **Cookie rotation**: Use multiple cookie sets for load balancing
3. **Metrics export**: Export cache metrics to monitoring system
4. **Scheduled refresh**: Refresh cookies before expiration





