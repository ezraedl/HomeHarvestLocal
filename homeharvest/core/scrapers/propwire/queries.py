"""
Queries and API endpoint definitions for Propwire.com

API Discovery Status: In Progress
Last Updated: 2025-01-31

Discovered Endpoints:
- POST https://api.propwire.com/api/auto_complete (autocomplete) ✅
- POST https://propwire.com/session-variable (session management) ✅
- GET https://propwire.com/search?filters={...} (search page) ✅
- POST https://api.propwire.com/api/property_search (property search) ✅ **CONFIRMED**

See API_DISCOVERY.md for investigation notes.
"""

# Base API URL
PROPWIRE_API_BASE = "https://api.propwire.com/api"

# Discovered Endpoints ✅
AUTO_COMPLETE_ENDPOINT = f"{PROPWIRE_API_BASE}/auto_complete"
SESSION_ENDPOINT = "https://propwire.com/session-variable"
SEARCH_PAGE_ENDPOINT = "https://propwire.com/search"

# ✅ CONFIRMED: Main property search endpoint (works unauthenticated)
PROPERTY_SEARCH_ENDPOINT = f"{PROPWIRE_API_BASE}/property_search"

# TODO: Discover and add:
# - Property details endpoint
# - Filter options endpoint
# - Export endpoint

# Placeholder endpoints (to be updated once discovered)
PROPERTY_DETAILS_ENDPOINT = f"{PROPWIRE_API_BASE}/property"  # Placeholder


def build_autocomplete_request(query: str) -> dict:
    """
    Build autocomplete API request.
    
    Args:
        query: Search query string
        
    Returns:
        Request payload dictionary
    """
    return {
        "query": query,
    }


def build_search_request(locations: list[dict], filters: dict = None, 
                         page: int = 1, limit: int = 200) -> dict:
    """
    Build property search API request.
    
    Args:
        locations: List of location dictionaries with searchType, county/city/zip, state, title
        filters: Dictionary of search filters
        page: Page number for pagination (1-indexed)
        limit: Results per page
        
    Returns:
        Request payload dictionary matching Propwire API format
    """
    # Propwire API uses size and result_index (0-indexed) instead of page/limit
    result_index = (page - 1) * limit
    
    request_data = {
        "size": limit,
        "result_index": result_index,
        "house": True,  # Include house properties (Propwire uses this flag)
        "locations": locations,
    }
    
    if filters:
        request_data.update(filters)
    
    return request_data


# Common ZIP code to state mapping (can be expanded or replaced with a lookup service)
ZIP_TO_STATE = {
    "46201": "IN",  # Indianapolis, IN
    # Add more as needed or use a proper ZIP code lookup service
}

def parse_location_string(location: str) -> dict:
    """
    Parse location string into Propwire location format.
    
    Args:
        location: Location string (e.g., "Dallas, TX", "Dallas County, TX", "75201")
        
    Returns:
        Location dictionary with searchType, county/city/zip, state, title
    """
    location = location.strip()
    
    # Try to parse different formats
    # Format: "City, State" or "County County, State"
    if "," in location:
        parts = [p.strip() for p in location.split(",")]
        if len(parts) >= 2:
            location_part = parts[0]
            state_part = parts[1]
            
            # Check if it's a county
            if "county" in location_part.lower():
                county = location_part.replace("County", "").replace("county", "").strip()
                return {
                    "searchType": "N",  # N for county/neighborhood
                    "county": county,
                    "state": state_part,
                    "title": location,
                }
            else:
                # Assume city
                return {
                    "searchType": "C",  # C for city
                    "city": location_part,
                    "state": state_part,
                    "title": location,
                }
    
    # Format: ZIP code
    if location.isdigit() and len(location) == 5:
        # Try to get state from ZIP code lookup
        state = ZIP_TO_STATE.get(location)
        title = f"{location}, {state}" if state else location
        
        return {
            "searchType": "Z",  # Z for zip
            "zip": location,
            "state": state,  # Will be None if not in lookup
            "title": title,
        }
    
    # Default: treat as city
    return {
        "searchType": "C",
        "city": location,
        "title": location,
    }


def build_property_details_request(property_id: str) -> dict:
    """
    Build property details API request.
    
    Args:
        property_id: Property identifier
        
    Returns:
        Request payload dictionary
    """
    # TODO: Update based on actual API structure
    return {
        "property_id": property_id,
    }

