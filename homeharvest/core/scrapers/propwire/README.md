# Propwire.com Scraper

## Status: Initial Implementation

This scraper follows the architecture pattern established by the Realtor.com scraper but is currently in the **investigation phase**. The structure is in place, but API endpoints and data field mappings need to be discovered.

## Current Implementation

### Files Created

1. **`__init__.py`**: `PropwireScraper` class with basic structure
   - API request handling with rate limiting (5-10 second delays)
   - Error handling for 403/DataDome blocking
   - Search and pagination framework
   - Placeholder for location handling

2. **`queries.py`**: Placeholder for API queries/endpoints
   - Needs actual Propwire API structure discovery

3. **`parsers.py`**: Data parsing functions
   - `parse_address()`: Extract address components
   - `parse_description()`: Extract property details
   - `parse_neighborhoods()`: Extract neighborhood info
   - `calculate_days_on_mls()`: Calculate days on market
   - `parse_dates()`: Parse date fields
   - **Note**: Field mappings are placeholders and need Propwire API investigation

4. **`processors.py`**: Property model creation
   - `process_property()`: Main property processing
   - `process_advertisers()`: Handle agent/broker data
   - `process_extra_property_details()`: Fetch additional details
   - **Note**: Field mappings are placeholders and need Propwire API investigation

## Next Steps

### Phase 1: API Investigation (Required)

1. **Discover Propwire API Structure**
   - Open Propwire.com in browser
   - Use DevTools Network tab to inspect requests
   - Identify:
     - API endpoints (GraphQL, REST, or other)
     - Request/response formats
     - Authentication requirements
     - Required headers

2. **Map Data Fields**
   - Document Propwire's field names
   - Map to Property model fields
   - Update parsers and processors

3. **Test Anti-Bot Bypass**
   - Test TLS fingerprinting effectiveness
   - Test with/without proxies
   - Adjust rate limiting if needed

### Phase 2: Implementation Updates

1. **Update `queries.py`**
   - Replace placeholders with actual API queries/endpoints
   - Implement query builders
   - Handle filters and pagination

2. **Update `parsers.py`**
   - Update field mappings based on actual API
   - Test with real Propwire responses
   - Handle edge cases

3. **Update `processors.py`**
   - Update field mappings
   - Test Property model creation
   - Handle missing data gracefully

4. **Update `__init__.py`**
   - Implement actual location handling
   - Update search logic
   - Test end-to-end flow

### Phase 3: Integration

1. **HomeHarvestLocal Integration**
   - Update main `__init__.py` to support Propwire
   - Add site selection logic
   - Test with `scrape_property()` function

2. **Testing**
   - Unit tests for parsers/processors
   - Integration tests for full flow
   - Test error handling

## Architecture Notes

This scraper follows the same pattern as the Realtor scraper:

```
API Request → Query Builder → Raw Response → Parser → Processor → Property Model
```

### Key Features

- **TLS Fingerprinting**: Uses `curl_cffi` with browser impersonation (inherited from base Scraper)
- **Rate Limiting**: 5-10 second delays (more conservative than Realtor due to DataDome)
- **Retry Logic**: Uses `tenacity` for exponential backoff
- **Parallel Processing**: ThreadPoolExecutor for concurrent property processing
- **Error Handling**: Graceful degradation with clear error messages

## Challenges

1. **DataDome Protection**: Propwire uses DataDome which is more aggressive than Realtor's protection
2. **API Discovery**: Need to reverse engineer Propwire's API structure
3. **Field Mapping**: Propwire's field names may differ significantly from Realtor
4. **Legal Considerations**: Review Propwire's Terms of Service before production use

## Usage (Once Complete)

```python
from homeharvest import scrape_property

# This will work once Propwire is fully integrated
properties = scrape_property(
    location="Dallas, TX",
    listing_type="for_sale",
    site="propwire.com"  # New parameter to select site
)
```

## References

- Realtor scraper: `../realtor/` (reference implementation)
- Proposal document: `../../../../real-estate-crm-scraper/docs/PROPWIRE_SCRAPER_PROPOSAL.md`
- Review summary: `../../../../real-estate-crm-scraper/docs/PROPWIRE_SCRAPER_REVIEW_SUMMARY.md`





