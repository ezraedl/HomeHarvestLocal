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

from .. import Scraper, DEFAULT_HEADERS, USE_CURL_CFFI, requests
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
        self.properties = []

    def search(self):
        """
        Perform the search using DOM scraping with Playwright.
        """
        import logging
        logger = logging.getLogger(__name__)
        from playwright.sync_api import sync_playwright

        logger.info(f"Starting Propwire DOM search for: {self.location}")

        with sync_playwright() as p:
            # 1. Launch Browser (Stealth)
            launch_options = {
                'headless': True,
                'args': [
                    '--disable-blink-features=AutomationControlled',
                    '--disable-extensions',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-infobars',
                    '--window-position=0,0',
                    '--ignore-certifcate-errors',
                    '--ignore-certifcate-errors-spki-list',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                ]
            }

            if self.proxy:
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
            
            # 2. Context with Stealth Scripts
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
            )
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ? Promise.resolve({ state: Notification.permission }) : originalQuery(parameters)
                );
            """)

            try:
                page = context.new_page()
                
                # 3. Navigate to Search
                logger.debug("Navigating to propwire.com/search...")
                page.goto('https://propwire.com/search', wait_until='domcontentloaded', timeout=60000)
                
                # 4. Input Location
                logger.debug(f"Typing location: {self.location}")
                # Wait for input
                try:
                    page.wait_for_selector('input[placeholder="City, County, Zip, or Address"]', timeout=10000)
                    page.fill('input[placeholder="City, County, Zip, or Address"]', self.location)
                except:
                    # Retry with generic input selector if specific placeholder fails
                    page.wait_for_selector('input[type="text"]', timeout=10000)
                    page.fill('input[type="text"]', self.location)

                # 5. Select from Autocomplete
                page.wait_for_timeout(2000) # Wait for suggestions
                page.keyboard.press("ArrowDown")
                page.keyboard.press("Enter")

                # 6. Wait for Results
                logger.debug("Waiting for results to load...")
                # Wait for the property list container or items
                # Inspecting typical behavior: there is usually a list of property cards
                # We'll wait for a common container class or just wait for network idle
                page.wait_for_timeout(5000) 
                
                # Check for "No results" or results
                # We can try to scroll to load more if needed, but for now just scrape first batch
                
                # 7. Extract Data from DOM
                # Use evaluate to extract data structure from the page
                logger.debug("Extracting property data from DOM...")
                
                properties_data = page.evaluate("""() => {
                    const results = [];
                    // Try to find property cards. Selectors might need adjustment based on site inspection.
                    // Assuming standard list structure. If classes are obfuscated, we might need robust selectors.
                    // Strategy: Look for elements that look like property cards (price, address)
                    
                    // Propwire specific: look for the list items
                    const cards = document.querySelectorAll('.results-list-item, [class*="PropertyCard"]');
                    
                    if (cards.length === 0) {
                         // Fallback: look for generic list items with price info
                         const genericCards = Array.from(document.querySelectorAll('div')).filter(d => d.innerText.includes('$') && d.innerText.includes('SqFt'));
                         // This is risky, but better than nothing if specific classes fail.
                         // Let's rely on the user testing/feedback for selector refinement.
                         return [];
                    }

                    cards.forEach(card => {
                        try {
                            const text = card.innerText;
                            const priceMatch = text.match(/\\$[0-9,]+/);
                            const price = priceMatch ? parseInt(priceMatch[0].replace(/[$,]/g, '')) : null;
                            
                            // Address usually at the top or bold
                            // Simple extraction: split by newlines
                            const lines = text.split('\\n').filter(l => l.trim().length > 0);
                            const address = lines[0] || ""; # Heuristic
                            
                            results.push({
                                address: address,
                                price: price,
                                raw: text
                            });
                        } catch (e) {}
                    });
                    return results;
                }""")
                
                logger.info(f"Found {len(properties_data)} raw property elements")
                
                # Convert to Property objects
                from ..models import Property, ListingType
                for p_data in properties_data:
                    try:
                        # Basic parsing logic - can be improved
                        prop = Property(
                            street_address=p_data.get('address'),
                            city=self.location, # Fallback
                            state="IN", # Fallback, should parse from address
                            zip_code=self.location if self.location.isdigit() else None,
                            price=p_data.get('price'),
                            listing_type=ListingType.FOR_SALE # Default
                        )
                        self.properties.append(prop)
                    except Exception as e:
                        logger.warning(f"Failed to parse property: {e}")

            except Exception as e:
                logger.error(f"DOM scraping failed: {e}")
                # Take screenshot for debugging?
                try:
                    page.screenshot(path="debug_dom_fail.png")
                except: pass
                raise e
            finally:
                browser.close()
        
        return self.properties

    def handle_location(self):
        # No-op in DOM scraper as location is handled in search interaction
        pass
    
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

            # Always re-initialize a clean session to avoid Realtor.com header contamination
            # from the Base Scraper class
            if USE_CURL_CFFI:
                # Use chrome120 as it matches our Playwright config and known working debug script
                self.session = requests.Session(impersonate="chrome120")
                logger.info("[HOMEHARVEST] Re-initialized fresh curl_cffi session for Propwire (chrome120)")
            else:
                self.session = requests.Session()
                logger.info("[HOMEHARVEST] Re-initialized fresh requests session for Propwire")

            # Re-configure proxies on the new session
            if self.proxy:
                proxies = {"http": self.proxy, "https": self.proxy}
                self.session.proxies.update(proxies)
            
            # Step 1: Try to get cached cookies (unless forcing refresh)
            if not force_refresh:
                cached_cookies = self._get_cached_cookies()
                if cached_cookies:
                    logger.info("Using cached DataDome cookies")
                    self.session.cookies.update(cached_cookies)
                    # Initialize session variable even with cached cookies
                    self._get_session_variable()
                    return
            
            # Step 2: Extract fresh cookies with Playwright
            logger.info("Extracting fresh DataDome cookies...")
            datadome_cookies = self._get_datadome_cookies_playwright()
            if datadome_cookies:
                logger.info("Successfully extracted DataDome cookies via Playwright")
                
                # Step 3: Cache the cookies for future use
                self._cache_cookies(datadome_cookies)
                
                # Step 4: Inject cookies into session
                # Remove metadata before injection
                cookie_metadata = datadome_cookies.pop('_metadata', {})
                logger.debug(f"Injecting {len(datadome_cookies)} cookies into session")
                
                # Inject cookies with proper domain/path information
                for name, value in datadome_cookies.items():
                    metadata = cookie_metadata.get(name, {})
                    domain = metadata.get('domain', '.propwire.com')
                    path = metadata.get('path', '/')
                    secure = metadata.get('secure', True)
                    
                    # Set cookie with proper domain and path
                    try:
                        self.session.cookies.set(name, value, domain=domain, path=path)
                        # Also set for common domain variations to ensure coverage
                        if name == 'datadome':
                            # Set for all possible domains
                            for alt_domain in ['.propwire.com', 'propwire.com', '.api.propwire.com', 'api.propwire.com']:
                                try:
                                    self.session.cookies.set(name, value, domain=alt_domain, path=path)
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.debug(f"Could not set cookie {name} with domain {domain}: {e}")
                        # Fallback: try simple update
                        try:
                            self.session.cookies.set(name, value)
                        except Exception:
                            pass
                
                # Also try update as fallback for any cookies that didn't get set
                try:
                    self.session.cookies.update(datadome_cookies)
                except Exception as e:
                    logger.debug(f"Cookie update fallback failed: {e}")

                # Verify cookies were set
                # curl_cffi sessions use RequestsCookieJar which supports .keys() and direct access
                try:
                    cookie_names = list(self.session.cookies.keys())
                except (AttributeError, TypeError):
                    # Fallback: try to get cookie names from cookie objects
                    cookie_names = [c.name for c in self.session.cookies if hasattr(c, 'name')]
                
                logger.debug(f"Cookies in session after injection: {cookie_names}")
                if 'datadome' in cookie_names:
                    logger.info("DataDome cookie successfully injected into session")
                else:
                    logger.warning("DataDome cookie NOT found in session after injection!")
                    # Try alternative verification: check if cookie value is accessible
                    try:
                        datadome_value = self.session.cookies.get('datadome')
                        if datadome_value:
                            logger.info(f"DataDome cookie value found via .get() method (length: {len(str(datadome_value))})")
                        else:
                            logger.warning("DataDome cookie value is None or empty")
                    except Exception as e:
                        logger.debug(f"Could not verify cookie via .get(): {e}")
                
                # Initialize application session using the injected cookies
                self._get_session_variable()
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
                    'args': [
                        '--disable-blink-features=AutomationControlled',
                        '--disable-extensions',
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-infobars',
                        '--window-position=0,0',
                        '--ignore-certifcate-errors',
                        '--ignore-certifcate-errors-spki-list',
                        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    ]
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
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US',
                    timezone_id='America/New_York',
                    has_touch=False,
                    is_mobile=False,
                    device_scale_factor=1,
                    color_scheme='light',
                )
                
                # Inject stealth scripts to hide automation
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    
                    // Overwrite the `plugins` property to use a custom getter.
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5],
                    });
                    
                    // Pass the Chrome Test.
                    window.chrome = {
                        runtime: {},
                        // etc.
                    };
                    
                    // Pass the Permissions Test.
                    const originalQuery = window.navigator.permissions.query;
                    return window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            originalQuery(parameters)
                    );
                """)
                
                page = context.new_page()
                
                # Navigate to propwire.com and wait for DataDome JS to execute
                logger.debug("Navigating to propwire.com...")
                page.goto('https://propwire.com/', wait_until='domcontentloaded', timeout=60000)
                
                # Simulate human behavior
                self._simulate_human_behavior(page)
                
                # Wait for DataDome cookie to appear
                logger.debug("Waiting for DataDome cookie...")
                try:
                    # Wait up to 10 seconds for the cookie to be set
                    page.wait_for_timeout(5000)
                except Exception as e:
                    logger.debug(f"Wait failed: {e}")
                
                # Navigate to search page to ensure all cookies are set
                logger.debug("Navigating to search page...")
                page.goto('https://propwire.com/search', wait_until='domcontentloaded', timeout=60000)
                self._simulate_human_behavior(page)
                
                # Extract all cookies with full metadata
                cookies = context.cookies()
                browser.close()
                
                # Convert to dictionary format (preserve full cookie info for proper injection)
                cookie_dict = {}
                cookie_metadata = {}  # Store full cookie info for proper domain/path setting
                for cookie in cookies:
                    cookie_dict[cookie['name']] = cookie['value']
                    cookie_metadata[cookie['name']] = {
                        'domain': cookie.get('domain', '.propwire.com'),
                        'path': cookie.get('path', '/'),
                        'secure': cookie.get('secure', True),
                        'httpOnly': cookie.get('httpOnly', False),
                    }
                
                # Check if we got DataDome cookie
                if 'datadome' in cookie_dict:
                    logger.info(f"Successfully extracted DataDome cookie (length: {len(cookie_dict['datadome'])})")
                    # Store metadata for proper injection
                    cookie_dict['_metadata'] = cookie_metadata
                    return cookie_dict
                else:
                    logger.warning(f"Playwright session established but no DataDome cookie found. Cookies: {list(cookie_dict.keys())}")
                    cookie_dict['_metadata'] = cookie_metadata
                    return cookie_dict  # Return anyway, might have other useful cookies
                    
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Playwright cookie extraction failed: {e}")
            return None

    def _simulate_human_behavior(self, page):
        """Simulate human-like mouse movements and scrolling."""
        import random
        try:
            # Random mouse movements
            for _ in range(3):
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                page.mouse.move(x, y, steps=10)
                page.wait_for_timeout(random.randint(100, 500))
            
            # Random scrolling
            page.evaluate("window.scrollBy(0, 300)")
            page.wait_for_timeout(random.randint(500, 1000))
            page.evaluate("window.scrollBy(0, -100)")
        except Exception:
            pass
    
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
        # Build clean headers for Propwire, AVOID DEFAULT_HEADERS which has Realtor info
        base_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
            'Origin': 'https://www.propwire.com',
            'Referer': 'https://www.propwire.com/',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            # Do NOT set User-Agent here, let curl_cffi session handle it to match TLS fingerprint
        }
        
        import logging
        logger = logging.getLogger(__name__)

        # Helper to inject cookies into headers
        def get_headers_with_cookies():
            current_headers = base_headers.copy()
            
            # Start with session cookies
            # Use manual dict comprehension to avoid compatibility issues with curl_cffi/requests aliases
            combined_cookies = {c.name: c.value for c in self.session.cookies if hasattr(c, 'name') and hasattr(c, 'value')}
            
            # Update with cached cookies (prioritizing Playwright-extracted DataDome)
            cached = self._get_cached_cookies()
            if cached:
                combined_cookies.update(cached)
            
            # Manually construct Cookie header with ALL merged cookies
            if combined_cookies:
                logger.debug(f"Constructing Cookie header with {len(combined_cookies)} cookies")
                cookie_header = "; ".join([f"{k}={v}" for k, v in combined_cookies.items()])
                current_headers['Cookie'] = cookie_header
            
            return current_headers

        try:
            # Initial request
            request_headers = get_headers_with_cookies()
            
            # Use session.post like Realtor does (session already has curl_cffi if available)
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
                    logger.warning("403 Forbidden received, refreshing cookies and retrying...")
                    self._establish_session(force_refresh=True)  # Force refresh cookies
                    time.sleep(2)
                    
                    # Re-fetch headers with NEW cookies
                    retry_headers = get_headers_with_cookies()
                    
                    response = self.session.post(
                        endpoint,
                        headers=retry_headers,
                        json=payload,
                        proxies=self.proxies
                    )
                    if response.status_code == 403:
                        logger.warning("Received 403 Forbidden (DataDome) on retry. Falling back to Playwright.")
                        return self._playwright_post_request(endpoint, payload)
            
            if response.status_code == 401:
                # 401 Unauthorized - cookies may have expired, try refreshing
                logger.warning("401 Unauthorized received, refreshing cookies and retrying...")
                self._establish_session(force_refresh=True)  # Force refresh cookies
                time.sleep(2)
                
                # Re-fetch headers with NEW cookies
                retry_headers = get_headers_with_cookies()
                
                response = self.session.post(
                    endpoint,
                    headers=retry_headers,
                    json=payload,
                    proxies=self.proxies
                )
                if response.status_code == 401:
                    logger.warning("Received 401 Unauthorized on retry. Falling back to Playwright.")
                    return self._playwright_post_request(endpoint, payload)
            
            response.raise_for_status()
            return response.json()
            
        except JSONDecodeError as e:
            raise Exception(f"Failed to parse JSON response: {e}")
        except Exception as e:
            # If we haven't already fallen back, maybe we should here too? 
            # For now just raise
            raise Exception(f"API request failed: {e}")

    def _playwright_post_request(self, endpoint: str, payload: dict) -> dict:
        """
        Execute POST request using Playwright to bypass DataDome.
        This is a fallback when curl_cffi is blocked.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError("Playwright is required for Propwire fallback but not installed.")

        import logging
        import json
        logger = logging.getLogger(__name__)

        logger.info("Initializing Playwright fallback session...")

        with sync_playwright() as p:
            # Launch browser with proxy if available
            launch_options = {
                'headless': True,
                'args': [
                    '--disable-blink-features=AutomationControlled',
                    '--disable-extensions',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-infobars',
                    '--window-position=0,0',
                    '--ignore-certifcate-errors',
                    '--ignore-certifcate-errors-spki-list',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                ]
            }
            
            # Configure proxy
            if self.proxy:
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
            
            # Create stealth context
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                has_touch=False,
                is_mobile=False,
                device_scale_factor=1,
                color_scheme='light',
            )
            
            # Inject stealth scripts
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                window.chrome = { runtime: {} };
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)
            
            page = context.new_page()
            
            logger.debug("Navigating to propwire.com (Playwright Fallback)...")
            try:
                # Navigate to main page first to establish session
                page.goto('https://propwire.com/', wait_until='domcontentloaded', timeout=60000)
                self._simulate_human_behavior(page)
                page.wait_for_timeout(2000)
                
                # Navigate to search page (mimics real user flow)
                logger.debug("Navigating to search page...")
                page.goto('https://propwire.com/search', wait_until='domcontentloaded', timeout=60000)
                self._simulate_human_behavior(page)
                page.wait_for_timeout(3000)  # Wait for DataDome to fully clear
                
                logger.debug(f"Executing fetch to {endpoint}...")
                
                # Execute fetch in the page context
                # Payload is already a dict, need to stringify it for JavaScript
                payload_json_str = json.dumps(payload)
                
                response_data = page.evaluate(f"""
                    async () => {{
                        const response = await fetch('{endpoint}', {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json',
                                'Accept': 'application/json',
                                'Origin': 'https://www.propwire.com',
                                'Referer': 'https://www.propwire.com/search'
                            }},
                            credentials: 'include',  // Include cookies
                            body: {payload_json_str}
                        }});
                        if (response.status === 403 || response.status === 401) {{
                            throw new Error('Fetch failed with status ' + response.status);
                        }}
                        return await response.json();
                    }}
                """)
                
                browser.close()
                return response_data
                
            except Exception as e:
                browser.close()
                logger.error(f"Playwright fallback failed: {e}")
                raise Exception(f"Playwright fallback failed: {e}")

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

