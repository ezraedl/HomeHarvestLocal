"""
homeharvest.propwire.__init__
~~~~~~~~~~~~

This module implements the scraper for propwire.com
"""

from __future__ import annotations

import json
import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from json import JSONDecodeError
from typing import Dict, Union, Optional
from threading import Lock

from tenacity import (
    retry,
    retry_if_exception_type,
    retry_if_not_exception_type,
    wait_exponential,
    stop_after_attempt,
)

from .. import Scraper, DEFAULT_HEADERS
from ....exceptions import AuthenticationError
from ..models import (
    Property,
    ListingType,
    ReturnType
)
# TODO: Import queries once Propwire API is discovered
# from .queries import (
#     PROPWIRE_SEARCH_QUERY,
#     PROPWIRE_PROPERTY_DETAILS_QUERY,
# )
from .queries import (
    PROPERTY_SEARCH_ENDPOINT,
    AUTO_COMPLETE_ENDPOINT,
    build_search_request,
    build_autocomplete_request,
    parse_location_string,
)
from .processors import (
    process_property,
    process_extra_property_details,
    get_key
)

# Cookie cache for DataDome cookies (shared across instances)
_cookie_cache: Dict[str, dict] = {}
_cookie_cache_lock = Lock()
_COOKIE_CACHE_TTL = timedelta(hours=12)  # DataDome cookies typically last 12-24 hours


class PropwireScraper(Scraper):
    """
    Scraper for Propwire.com following the Realtor scraper architecture.
    """
    SEARCH_API_URL = PROPERTY_SEARCH_ENDPOINT
    AUTO_COMPLETE_URL = AUTO_COMPLETE_ENDPOINT
    NUM_PROPERTY_WORKERS = 20
    DEFAULT_PAGE_SIZE = 200
    
    # Class-level Redis client (optional, shared across instances)
    _redis_client = None
    _redis_available = False

    def __init__(self, scraper_input):
        super().__init__(scraper_input)
        # Initialize Redis client if available (only once)
        self._init_redis_if_available()
        # Propwire requires session establishment (unlike Realtor which can work without it)
        # Establish session by visiting the site first to get cookies
        self._establish_session()
    
    @classmethod
    def _init_redis_if_available(cls):
        """Initialize Redis client if available (only once)."""
        if cls._redis_client is not None:
            return  # Already initialized
        
        try:
            import redis
            import os
            
            # Try to get Redis URL from environment
            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
            
            # Parse Redis URL
            if redis_url.startswith('redis://'):
                from urllib.parse import urlparse
                parsed = urlparse(redis_url)
                cls._redis_client = redis.Redis(
                    host=parsed.hostname or 'localhost',
                    port=parsed.port or 6379,
                    db=int(parsed.path.lstrip('/')) if parsed.path else 0,
                    password=parsed.password,
                    decode_responses=False,  # We'll handle JSON encoding/decoding
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                # Test connection
                cls._redis_client.ping()
                cls._redis_available = True
                import logging
                logging.getLogger(__name__).info("Redis available for cookie caching")
            else:
                cls._redis_available = False
        except Exception as e:
            # Redis not available or connection failed - use in-memory cache
            cls._redis_available = False
            import logging
            logging.getLogger(__name__).debug(f"Redis not available for cookie caching: {e}")
    
    @classmethod
    def _get_cached_cookies(cls, cache_key: str = "propwire_datadome_cookies") -> Optional[dict]:
        """
        Get cached DataDome cookies.
        
        Args:
            cache_key: Cache key for cookies
            
        Returns:
            Dictionary of cookies or None if not cached/expired
        """
        try:
            # Try Redis first
            if cls._redis_available and cls._redis_client:
                try:
                    cached = cls._redis_client.get(cache_key)
                    if cached:
                        data = json.loads(cached)
                        # Check expiration
                        timestamp = datetime.fromisoformat(data['timestamp'])
                        if datetime.now() - timestamp < _COOKIE_CACHE_TTL:
                            import logging
                            logging.getLogger(__name__).debug(f"Using cached DataDome cookies from Redis (age: {datetime.now() - timestamp})")
                            return data['cookies']
                        else:
                            # Expired, delete from cache
                            cls._redis_client.delete(cache_key)
                            import logging
                            logging.getLogger(__name__).debug("Cached cookies expired, will refresh")
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Redis cache read failed: {e}, falling back to in-memory cache")
            
            # Fallback to in-memory cache
            with _cookie_cache_lock:
                if cache_key in _cookie_cache:
                    cached_data = _cookie_cache[cache_key]
                    timestamp = datetime.fromisoformat(cached_data['timestamp'])
                    if datetime.now() - timestamp < _COOKIE_CACHE_TTL:
                        import logging
                        logging.getLogger(__name__).debug(f"Using cached DataDome cookies from memory (age: {datetime.now() - timestamp})")
                        return cached_data['cookies']
                    else:
                        # Expired, remove from cache
                        del _cookie_cache[cache_key]
                        import logging
                        logging.getLogger(__name__).debug("Cached cookies expired, will refresh")
            
            return None
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Error reading cookie cache: {e}")
            return None
    
    @classmethod
    def _cache_cookies(cls, cookies: dict, cache_key: str = "propwire_datadome_cookies"):
        """
        Cache DataDome cookies.
        
        Args:
            cookies: Dictionary of cookies to cache
            cache_key: Cache key for cookies
        """
        try:
            cache_data = {
                'cookies': cookies,
                'timestamp': datetime.now().isoformat()
            }
            
            # Try Redis first
            if cls._redis_available and cls._redis_client:
                try:
                    # Cache for 12 hours (43200 seconds)
                    cls._redis_client.setex(
                        cache_key,
                        43200,  # 12 hours in seconds
                        json.dumps(cache_data)
                    )
                    import logging
                    logging.getLogger(__name__).info(f"Cached DataDome cookies in Redis (TTL: 12 hours)")
                    return
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Redis cache write failed: {e}, falling back to in-memory cache")
            
            # Fallback to in-memory cache
            with _cookie_cache_lock:
                _cookie_cache[cache_key] = cache_data
                import logging
                logging.getLogger(__name__).info(f"Cached DataDome cookies in memory (TTL: 12 hours)")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Error caching cookies: {e}")

    def _establish_session(self, force_refresh: bool = False):
        """
        Establish a session by visiting Propwire.com to get necessary cookies.
        This is needed to pass DataDome protection.
        
        Strategy:
        1. Check cached cookies (Redis or in-memory)
        2. If cached and not expired, use them
        3. If not cached or expired, extract with Playwright
        4. Cache extracted cookies for reuse
        5. Fallback to requests-based if Playwright unavailable
        
        Args:
            force_refresh: If True, skip cache and force fresh cookie extraction
        """
        try:
            import logging
            logger = logging.getLogger(__name__)
            
            # Step 1: Try to get cached cookies (unless forcing refresh)
            if not force_refresh:
                cached_cookies = self._get_cached_cookies()
                if cached_cookies:
                    logger.info("Using cached DataDome cookies")
                    # Inject cached cookies into session
                    for name, value in cached_cookies.items():
                        self.session.cookies.set(name, value, domain='.propwire.com')
                    # Also set for api.propwire.com
                    for name, value in cached_cookies.items():
                        self.session.cookies.set(name, value, domain='.api.propwire.com')
                    return
            
            # Step 2: Extract fresh cookies with Playwright
            logger.info("Extracting fresh DataDome cookies...")
            datadome_cookies = self._get_datadome_cookies_playwright()
            if datadome_cookies:
                logger.info("Successfully extracted DataDome cookies via Playwright")
                
                # Step 3: Cache the cookies for future use
                self._cache_cookies(datadome_cookies)
                
                # Step 4: Inject cookies into session
                logger.debug(f"Injecting {len(datadome_cookies)} cookies into session")
                for name, value in datadome_cookies.items():
                    self.session.cookies.set(name, value, domain='.propwire.com')
                # Also set for api.propwire.com
                for name, value in datadome_cookies.items():
                    self.session.cookies.set(name, value, domain='.api.propwire.com')
                
                # Verify cookies were set
                cookie_names = [c.name for c in self.session.cookies if hasattr(c, 'name')]
                logger.debug(f"Cookies in session after injection: {cookie_names}")
                if 'datadome' in cookie_names:
                    logger.info("DataDome cookie successfully injected into session")
                else:
                    logger.warning("DataDome cookie NOT found in session after injection!")
                
                return
            
            # Step 5: Fallback to requests-based session establishment
            logger.debug("Playwright not available or failed, using requests-based session establishment...")
            self._establish_session_requests()
            
        except Exception as e:
            # Log but don't fail - cookies might still work
            import logging
            logging.getLogger(__name__).warning(f"Session establishment warning: {e}")
    
    def _get_datadome_cookies_playwright(self):
        """
        Extract DataDome cookies using Playwright (executes JavaScript).
        
        Returns:
            Dictionary of cookies or None if Playwright not available
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            import logging
            logging.getLogger(__name__).debug("Playwright not installed, skipping cookie extraction")
            return None
        
        try:
            import logging
            logger = logging.getLogger(__name__)
            
            logger.debug("Using Playwright to extract DataDome cookies...")
            
            with sync_playwright() as p:
                # Launch browser with proxy if available
                launch_options = {
                    'headless': True,
                }
                
                # Configure proxy if available
                if self.proxy:
                    # Parse proxy URL (format: http://user:pass@host:port)
                    from urllib.parse import urlparse
                    parsed = urlparse(self.proxy)
                    launch_options['proxy'] = {
                        'server': f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                        'username': parsed.username,
                        'password': parsed.password,
                    } if parsed.username else {
                        'server': self.proxy
                    }
                
                browser = p.chromium.launch(**launch_options)
                
                # Create context with realistic browser settings
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1200},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US',
                    timezone_id='America/New_York',
                )
                
                page = context.new_page()
                
                # Navigate to propwire.com and wait for DataDome JS to execute
                logger.debug("Navigating to propwire.com...")
                page.goto('https://propwire.com/', wait_until='networkidle', timeout=30000)
                time.sleep(5)  # Wait for DataDome JS to execute and set cookies
                
                # Navigate to search page
                logger.debug("Navigating to search page...")
                page.goto('https://propwire.com/search', wait_until='networkidle', timeout=30000)
                time.sleep(3)  # Wait for additional cookies
                
                # Extract all cookies
                cookies = context.cookies()
                browser.close()
                
                # Convert to dictionary format
                cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
                
                # Check if we got DataDome cookie
                if 'datadome' in cookie_dict:
                    logger.info(f"Successfully extracted DataDome cookie (length: {len(cookie_dict['datadome'])})")
                    return cookie_dict
                else:
                    logger.warning("Playwright session established but no DataDome cookie found")
                    return cookie_dict  # Return anyway, might have other useful cookies
                    
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Playwright cookie extraction failed: {e}")
            return None
    
    def _establish_session_requests(self):
        """
        Fallback: Establish session using requests (no JavaScript execution).
        This is less reliable but doesn't require Playwright.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Visit the main page to establish session and get cookies
        logger.debug("Establishing session: visiting propwire.com...")
        response = self.session.get(
            "https://propwire.com/",
            headers={
                'User-Agent': DEFAULT_HEADERS.get('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            proxies=self.proxies,
            timeout=15
        )
        logger.debug(f"Initial visit status: {response.status_code}, cookies: {len(self.session.cookies)}")
        
        # Small delay after initial visit to let DataDome process
        time.sleep(5)  # Longer delay for DataDome to process
        
        # Also visit the search page to ensure we have all necessary cookies
        logger.debug("Visiting search page to get additional cookies...")
        response2 = self.session.get(
            "https://propwire.com/search",
            headers={
                'User-Agent': DEFAULT_HEADERS.get('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://propwire.com/',
            },
            proxies=self.proxies,
            timeout=15
        )
        logger.debug(f"Search page visit status: {response2.status_code}, total cookies: {len(self.session.cookies)}")
        # List cookie names for debugging
        try:
            cookie_names = [c.name if hasattr(c, 'name') else str(c) for c in self.session.cookies]
            logger.debug(f"Cookie names: {cookie_names}")
        except:
            logger.debug(f"Cookies: {list(self.session.cookies.keys()) if hasattr(self.session.cookies, 'keys') else 'unknown'}")
        time.sleep(2)  # Delay before session-variable call
        
        # Call session-variable endpoint (browser does this before API calls)
        self._get_session_variable()
        
        time.sleep(3)  # Final delay for DataDome

    def _get_session_variable(self):
        """
        Call the session-variable endpoint to get session token.
        This might be needed for API authentication.
        """
        try:
            import logging
            logger = logging.getLogger(__name__)
            
            from .queries import SESSION_ENDPOINT
            
            logger.debug("Calling session-variable endpoint...")
            response = self.session.post(
                SESSION_ENDPOINT,
                headers={
                    'User-Agent': DEFAULT_HEADERS.get('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
                    'Content-Type': 'application/json',
                    'Origin': 'https://www.propwire.com',
                    'Referer': 'https://www.propwire.com/',
                    'Accept': 'application/json',
                },
                proxies=self.proxies,
                timeout=15
            )
            logger.debug(f"Session-variable endpoint status: {response.status_code}")
            if response.status_code == 200:
                try:
                    session_data = response.json()
                    logger.debug(f"Session data received: {session_data}")
                except:
                    pass
            time.sleep(1)
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"Session-variable call warning: {e}")

    def _rest_post(self, endpoint: str, payload: dict) -> dict:
        """
        Execute a REST POST request to Propwire.com.
        Uses the same pattern as Realtor scraper - direct API calls with session.
        
        Args:
            endpoint: The API endpoint URL
            payload: Request body dictionary
            
        Returns:
            Response JSON dictionary
        """
        # Add randomized delay to avoid rate limiting (3-8 seconds, same as Realtor)
        # Increased delay to make requests look more human-like
        delay = random.uniform(3.0, 8.0)
        time.sleep(delay)
        
        # Use session from base class (like Realtor does) - it already has curl_cffi configured
        # Build headers similar to Realtor's DEFAULT_HEADERS but for Propwire
        # Key: Use the same header structure as Realtor (which works) but with Propwire domains
        request_headers = DEFAULT_HEADERS.copy()
        request_headers.update({
            'Origin': 'https://www.propwire.com',
            'Referer': 'https://www.propwire.com/',
            'Accept': 'application/json, text/plain, */*',  # Propwire expects JSON, not */*
        })
        
        try:
            # Verify cookies before making request
            import logging
            logger = logging.getLogger(__name__)
            cookie_names = [c.name for c in self.session.cookies if hasattr(c, 'name')]
            logger.debug(f"Cookies in session before API call: {cookie_names}")
            if 'datadome' not in cookie_names:
                logger.warning("DataDome cookie missing before API call! This may cause 401/403 errors.")
            
            # Use session.post like Realtor does (session already has curl_cffi if available)
            # Realtor pattern: use session.post with headers, session already configured with curl_cffi
            response = self.session.post(
                endpoint,
                headers=request_headers,
                json=payload,
                proxies=self.proxies
            )
            
            # Handle errors - same pattern as Realtor
            if response.status_code == 403:
                if not self.proxy:
                    raise AuthenticationError(
                        "Received 403 Forbidden from Propwire.com API. DataDome blocking detected.",
                        response=response
                    )
                else:
                    # With proxy, try refreshing cookies and retry once
                    import logging
                    logging.getLogger(__name__).warning("403 Forbidden received, refreshing cookies and retrying...")
                    self._establish_session(force_refresh=True)  # Force refresh cookies
                    time.sleep(2)
                    response = self.session.post(
                        endpoint,
                        headers=request_headers,
                        json=payload,
                        proxies=self.proxies
                    )
                    if response.status_code == 403:
                        raise AuthenticationError(
                            "Received 403 Forbidden from Propwire.com API. DataDome blocking detected.",
                            response=response
                        )
            
            if response.status_code == 401:
                # 401 Unauthorized - cookies may have expired, try refreshing
                import logging
                logging.getLogger(__name__).warning("401 Unauthorized received, refreshing cookies and retrying...")
                self._establish_session(force_refresh=True)  # Force refresh cookies
                time.sleep(2)
                response = self.session.post(
                    endpoint,
                    headers=request_headers,
                    json=payload,
                    proxies=self.proxies
                )
                if response.status_code == 401:
                    raise AuthenticationError(
                        "Received 401 Unauthorized from Propwire.com API. Session may have expired or authentication required.",
                        response=response
                    )
            
            response.raise_for_status()
            return response.json()
            
        except JSONDecodeError as e:
            raise Exception(f"Failed to parse JSON response: {e}")
        except Exception as e:
            raise Exception(f"API request failed: {e}")

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        stop=stop_after_attempt(3),
    )
    def handle_location(self):
        """
        Resolve location string to Propwire's location format using autocomplete API.
        
        Returns:
            Dictionary with location information or None
        """
        try:
            payload = build_autocomplete_request(self.location)
            response_json = self._rest_post(self.AUTO_COMPLETE_URL, payload)
            
            if not response_json or "data" not in response_json or not response_json["data"]:
                # Fallback: try to parse location string directly
                import logging
                logging.getLogger(__name__).debug(f"Autocomplete returned no data, using fallback parsing")
                return parse_location_string(self.location)
            
            # Use the first result (most relevant)
            location_data = response_json["data"][0]
            
            # Debug: log the location_data to see what we're getting
            import logging
            logging.getLogger(__name__).debug(f"Autocomplete response data: {location_data}")
            
            # Extract location info from autocomplete response
            # Format may vary, so we try multiple field names
            # Propwire autocomplete likely returns: {searchType, county/city/zip, state, title}
            title = location_data.get("title") or location_data.get("display_name") or self.location
            location_info = {
                "searchType": location_data.get("searchType") or location_data.get("type") or "C",
                "title": title,
            }
            
            # Extract state from title first (e.g., "46201, IN" -> "IN")
            if "," in title:
                parts = title.split(",")
                if len(parts) >= 2:
                    location_info["state"] = parts[-1].strip()
            
            # Override with explicit state from location_data if available
            if location_data.get("state") or location_data.get("state_code"):
                location_info["state"] = location_data.get("state") or location_data.get("state_code")
            
            # Add location-specific fields based on searchType
            search_type = location_info["searchType"]
            if search_type == "N":  # County/Neighborhood
                if location_data.get("county"):
                    location_info["county"] = location_data["county"]
            elif search_type == "C":  # City
                if location_data.get("city"):
                    location_info["city"] = location_data["city"]
            elif search_type == "Z":  # ZIP
                if location_data.get("zip") or location_data.get("zip_code"):
                    location_info["zip"] = location_data.get("zip") or location_data.get("zip_code")
            
            return location_info
            
        except Exception as e:
            # Fallback: parse location string directly
            import logging
            logging.getLogger(__name__).debug(f"Autocomplete failed ({e}), using fallback parsing")
            location_info = parse_location_string(self.location)
            
            # If it's a ZIP code and we have state from lookup, use it
            if location_info.get("searchType") == "Z" and location_info.get("state"):
                # Update title to include state
                location_info["title"] = f"{location_info['zip']}, {location_info['state']}"
            
            return location_info

    def get_property_details(self, property_id: str) -> dict:
        """
        Fetch detailed information for a single property.
        
        Args:
            property_id: Propwire property identifier
            
        Returns:
            Property details dictionary
        """
        # TODO: Implement once Propwire API structure is known
        endpoint = f"{self.PROPERTY_API_URL}/{property_id}"
        
        try:
            data = self._api_request(endpoint, method="GET")
            return data
        except Exception as e:
            # Log error but don't fail completely
            return {}

    def general_search(self, variables: dict, search_type: str) -> Dict[str, Union[int, Union[list[Property], list[dict]]]]:
        """
        Handles a location area & returns a list of properties.
        
        Args:
            variables: Search parameters including locations, page, limit
            search_type: Type of search (area, comps, address)
            
        Returns:
            Dictionary with 'total' count and 'properties' list
        """
        try:
            # Build search request payload
            locations = variables.get("locations", [])
            page = variables.get("page", 1)
            limit = variables.get("limit", self.DEFAULT_PAGE_SIZE)
            
            payload = build_search_request(locations, filters=variables.get("filters"), page=page, limit=limit)
            
            # Make API request
            response_data = self._rest_post(self.SEARCH_API_URL, payload)
            
            # Parse response - Propwire API structure:
            # { "response": [...], "result_count": 14875, "record_count": 250, ... }
            properties_list = []
            total_properties = 0
            
            # Propwire returns properties in "response" array
            if "response" in response_data and isinstance(response_data["response"], list):
                properties_list = response_data["response"]
                # Get total from result_count
                total_properties = response_data.get("result_count", len(properties_list))
            # Fallback: try other possible formats
            elif "data" in response_data:
                if isinstance(response_data["data"], list):
                    properties_list = response_data["data"]
                elif isinstance(response_data["data"], dict):
                    properties_list = response_data["data"].get("properties", []) or response_data["data"].get("results", [])
                    total_properties = response_data["data"].get("total", 0) or response_data["data"].get("count", 0)
            elif "properties" in response_data:
                properties_list = response_data["properties"]
                total_properties = response_data.get("total", len(properties_list))
            elif "results" in response_data:
                properties_list = response_data["results"]
                total_properties = response_data.get("total", len(properties_list))
            else:
                # Assume the response itself is a list
                if isinstance(response_data, list):
                    properties_list = response_data
                    total_properties = len(properties_list)
            
            # Get total from response if not already set
            if not total_properties:
                total_properties = response_data.get("result_count") or response_data.get("total") or response_data.get("count") or len(properties_list)
            
            # Process properties
            properties: list[Union[Property, dict]] = []
            
            if self.return_type != ReturnType.raw:
                with ThreadPoolExecutor(max_workers=self.NUM_PROPERTY_WORKERS) as executor:
                    futures_with_indices = [
                        (i, executor.submit(
                            process_property, 
                            result, 
                            self.mls_only, 
                            self.extra_property_data,
                            self.exclude_pending, 
                            self.listing_type, 
                            get_key, 
                            process_extra_property_details
                        ))
                        for i, result in enumerate(properties_list)
                    ]
                    
                    results = []
                    for idx, future in futures_with_indices:
                        result = future.result()
                        if result:
                            results.append((idx, result))
                    
                    results.sort(key=lambda x: x[0])
                    properties = [result for idx, result in results]
            else:
                properties = properties_list
            
            return {
                "total": total_properties,
                "properties": properties,
            }
            
        except Exception as e:
            # Log error but return empty result
            import logging
            logging.getLogger(__name__).error(f"Propwire search error: {e}")
            return {"total": 0, "properties": []}

    def search(self):
        """
        Main search entry point.
        
        Returns:
            List of Property objects or raw dictionaries
        """
        location_info = self.handle_location()
        if not location_info:
            return []

        # Visit search page with location in URL (like browser does) to establish session
        # This helps DataDome recognize us as a legitimate user
        try:
            import json
            import urllib.parse
            filters_json = json.dumps({"locations": [location_info]})
            filters_encoded = urllib.parse.quote(filters_json)
            search_url = f"https://propwire.com/search?filters={filters_encoded}"
            
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Visiting search page with location to establish session: {search_url[:100]}...")
            
            response = self.session.get(
                search_url,
                headers={
                    'User-Agent': DEFAULT_HEADERS.get('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': 'https://propwire.com/',
                },
                proxies=self.proxies,
                timeout=15
            )
            logger.debug(f"Search page visit status: {response.status_code}")
            time.sleep(2)  # Wait after visiting search page
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"Failed to visit search page (non-critical): {e}")

        # Convert location_info to list format expected by API
        locations = [location_info]
        
        # Calculate page number from offset
        page = (self.offset // self.DEFAULT_PAGE_SIZE) + 1
        
        search_variables = {
            "locations": locations,
            "page": page,
            "limit": self.DEFAULT_PAGE_SIZE,
        }
        
        # Add filters if specified
        filters = {}
        if self.price_min is not None:
            filters["price_min"] = self.price_min
        if self.price_max is not None:
            filters["price_max"] = self.price_max
        if self.beds_min is not None:
            filters["beds_min"] = self.beds_min
        if self.baths_min is not None:
            filters["baths_min"] = self.baths_min
        if self.sqft_min is not None:
            filters["sqft_min"] = self.sqft_min
        if filters:
            search_variables["filters"] = filters
        
        # Determine search type
        search_type = "area"  # Default for Propwire
        
        result = self.general_search(search_variables, search_type=search_type)
        total = result["total"]
        homes = result["properties"]
        
        # Handle pagination (Propwire uses page-based pagination)
        total_pages = (total + self.DEFAULT_PAGE_SIZE - 1) // self.DEFAULT_PAGE_SIZE if total > 0 else 0
        max_page = min(total_pages, (self.offset + self.limit + self.DEFAULT_PAGE_SIZE - 1) // self.DEFAULT_PAGE_SIZE)
        
        if page < max_page:
            if self.parallel:
                # Parallel mode: Fetch all remaining pages in parallel
                with ThreadPoolExecutor() as executor:
                    futures_with_pages = [
                        (p, executor.submit(
                            self.general_search,
                            variables={**search_variables, "page": p},
                            search_type=search_type,
                        ))
                        for p in range(page + 1, max_page + 1)
                    ]
                    
                    results = []
                    for page_num, future in futures_with_pages:
                        results.append((page_num, future.result()["properties"]))
                    
                    results.sort(key=lambda x: x[0])
                    for page_num, properties in results:
                        homes.extend(properties)
            else:
                # Sequential mode: Fetch pages one by one
                for current_page in range(page + 1, max_page + 1):
                    result = self.general_search(
                        variables={**search_variables, "page": current_page},
                        search_type=search_type,
                    )
                    page_properties = result["properties"]
                    homes.extend(page_properties)
        
        return homes

