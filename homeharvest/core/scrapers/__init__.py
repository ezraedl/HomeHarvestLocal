from __future__ import annotations
from typing import Union
import random

# Try to use curl_cffi for TLS fingerprinting (anti-bot measures)
import logging
logger = logging.getLogger(__name__)

# List of impersonation profiles to rotate through for diversity
# This prevents all requests from having the same TLS fingerprint
IMPERSONATE_PROFILES = [
    "chrome120",      # Latest Chrome - most common in real traffic
    "chrome116",      # Stable Chrome - widely used
    "chrome110",      # Older Chrome - less common in bots
    "safari15_3",     # Safari - different fingerprint
    "safari15_5",     # Newer Safari
    "edge99",         # Edge - fallback option
    "edge101",        # Newer Edge
]

def get_random_impersonate() -> str:
    """
    Get a random impersonation profile for diversity.
    This helps avoid detection by using different TLS fingerprints.
    """
    return random.choice(IMPERSONATE_PROFILES)

try:
    from curl_cffi import requests
    # curl_cffi.requests is compatible with requests API, but adapters come from standard requests
    from requests.adapters import HTTPAdapter
    USE_CURL_CFFI = True
    # Use chrome120 as default - less flagged than edge99, more common in real traffic
    # Individual sessions will use get_random_impersonate() for rotation
    DEFAULT_IMPERSONATE = "chrome120"  # Default fallback (but prefer rotation)
    # Log that curl_cffi is being used (only log once at module import)
    logger.info(f"[HOMEHARVEST] curl_cffi enabled with impersonate rotation (default: {DEFAULT_IMPERSONATE})")
except ImportError as e:
    import requests
    from requests.adapters import HTTPAdapter
    USE_CURL_CFFI = False
    DEFAULT_IMPERSONATE = None
    # Log that curl_cffi is not available with error details
    logger.warning(f"[HOMEHARVEST] curl_cffi not available - using standard requests library. ImportError: {str(e)}")
except Exception as e:
    # Catch any other errors during import (e.g., missing system dependencies)
    import requests
    from requests.adapters import HTTPAdapter
    USE_CURL_CFFI = False
    DEFAULT_IMPERSONATE = None
    logger.error(f"[HOMEHARVEST] curl_cffi import failed with unexpected error: {type(e).__name__}: {str(e)}. Falling back to standard requests library.")

# Note: requests is already imported above (either curl_cffi.requests or standard requests)
# Do NOT import requests here as it would overwrite curl_cffi.requests
import uuid
from urllib3.util.retry import Retry
from ...exceptions import AuthenticationError
from .models import Property, ListingType, SiteName, SearchPropertyType, ReturnType
import json
from pydantic import BaseModel


DEFAULT_HEADERS = {
    'Content-Type': 'application/json',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
    'Origin': 'https://www.realtor.com',
    'Pragma': 'no-cache',
    'Referer': 'https://www.realtor.com/',
    'rdc-client-name': 'RDC_WEB_SRP_FS_PAGE',
    'rdc-client-version': '3.0.2515',
    'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
    'x-is-bot': 'false',
}


class ScraperInput(BaseModel):
    location: str
    listing_type: ListingType | list[ListingType] | None
    property_type: list[SearchPropertyType] | None = None
    radius: float | None = None
    mls_only: bool | None = False
    proxy: str | None = None
    last_x_days: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    date_from_precision: str | None = None  # "day" or "hour"
    date_to_precision: str | None = None    # "day" or "hour"
    foreclosure: bool | None = False
    extra_property_data: bool | None = True
    exclude_pending: bool | None = False
    limit: int = 10000
    offset: int = 0
    return_type: ReturnType = ReturnType.pandas

    # New date/time filtering parameters
    past_hours: int | None = None

    # New last_update_date filtering parameters
    updated_since: str | None = None
    updated_in_past_hours: int | None = None

    # New property filtering parameters
    beds_min: int | None = None
    beds_max: int | None = None
    baths_min: float | None = None
    baths_max: float | None = None
    sqft_min: int | None = None
    sqft_max: int | None = None
    price_min: int | None = None
    price_max: int | None = None
    lot_sqft_min: int | None = None
    lot_sqft_max: int | None = None
    year_built_min: int | None = None
    year_built_max: int | None = None

    # New sorting parameters
    sort_by: str | None = None
    sort_direction: str = "desc"

    # Pagination control
    parallel: bool = True


class Scraper:
    session = None  # Class-level shared session
    
    def __init__(
        self,
        scraper_input: ScraperInput,
    ):
        self.location = scraper_input.location
        self.listing_type = scraper_input.listing_type
        self.property_type = scraper_input.property_type

        self.proxy = scraper_input.proxy
        
        # Create a fresh session per instance when using proxies (better for curl_cffi TLS fingerprinting)
        # or use shared session when no proxy is needed
        if self.proxy:
            # Create a new session for this instance with proxy
            if USE_CURL_CFFI:
                impersonate_profile = get_random_impersonate()
                self.session = requests.Session(impersonate=impersonate_profile)
                logger.info(f"[HOMEHARVEST] Created new curl_cffi session with impersonate={impersonate_profile} for proxy")
            else:
                self.session = requests.Session()
                retries = Retry(
                    total=3, backoff_factor=4, status_forcelist=[429], allowed_methods=frozenset(["GET", "POST"])
                )
                adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=20)
                self.session.mount("http://", adapter)
                self.session.mount("https://", adapter)
            
            # Set headers
            self.session.headers.update(
                {
                    'Content-Type': 'application/json',
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Cache-Control': 'no-cache',
                    'Origin': 'https://www.realtor.com',
                    'Pragma': 'no-cache',
                    'Referer': 'https://www.realtor.com/',
                    'rdc-client-name': 'RDC_WEB_SRP_FS_PAGE',
                    'rdc-client-version': '3.0.2515',
                    'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"macOS"',
                    'sec-fetch-dest': 'empty',
                    'sec-fetch-mode': 'cors',
                    'sec-fetch-site': 'same-site',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Upgrade-Insecure-Requests': '1',
                    'x-is-bot': 'false',
                }
            )
            
            # Configure proxy
            proxies = {"http": self.proxy, "https": self.proxy}
            self.session.proxies.update(proxies)
            logger.info(f"[HOMEHARVEST] Session proxy configured: {self.proxy[:50]}... (session type: {type(self.session).__module__}.{type(self.session).__name__})")
        else:
            # Use shared session when no proxy is needed
            if not Scraper.session:
                if USE_CURL_CFFI:
                    impersonate_profile = get_random_impersonate()
                    Scraper.session = requests.Session(impersonate=impersonate_profile)
                    logger.info(f"[HOMEHARVEST] Created shared curl_cffi session with impersonate={impersonate_profile}")
                else:
                    Scraper.session = requests.Session()
                    retries = Retry(
                        total=3, backoff_factor=4, status_forcelist=[429], allowed_methods=frozenset(["GET", "POST"])
                    )
                    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=20)
                    Scraper.session.mount("http://", adapter)
                    Scraper.session.mount("https://", adapter)
                Scraper.session.headers.update(
                    {
                        'Content-Type': 'application/json',
                        'apollographql-client-version': '26.11.1-26.11.1.1106489',
                        'Accept': '*/*',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'rdc-client-version': '26.11.1',
                        'X-APOLLO-OPERATION-TYPE': 'query',
                        'X-APOLLO-OPERATION-ID': 'null',
                        'rdc-client-name': 'RDC_NATIVE_MOBILE-iPhone-com.move.Realtor',
                        'apollographql-client-name': 'com.move.Realtor-apollo-ios',
                        'User-Agent': 'Realtor.com/26.11.1.1106489 CFNetwork/3860.200.71 Darwin/25.1.0',
                    }
                )
            self.session = Scraper.session
            logger.debug(f"[HOMEHARVEST] Using shared session (no proxy, session type: {type(self.session).__module__}.{type(self.session).__name__})")
        self.proxy = scraper_input.proxy
        self.proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None

        self.listing_type = scraper_input.listing_type
        self.radius = scraper_input.radius
        self.last_x_days = scraper_input.last_x_days
        self.mls_only = scraper_input.mls_only
        self.date_from = scraper_input.date_from
        self.date_to = scraper_input.date_to
        self.date_from_precision = scraper_input.date_from_precision
        self.date_to_precision = scraper_input.date_to_precision
        self.foreclosure = scraper_input.foreclosure
        self.extra_property_data = False  # TODO: temporarily disabled
        self.exclude_pending = scraper_input.exclude_pending
        self.limit = scraper_input.limit
        self.offset = scraper_input.offset
        self.return_type = scraper_input.return_type

        # New date/time filtering
        self.past_hours = scraper_input.past_hours

        # New last_update_date filtering
        self.updated_since = scraper_input.updated_since
        self.updated_in_past_hours = scraper_input.updated_in_past_hours

        # New property filtering
        self.beds_min = scraper_input.beds_min
        self.beds_max = scraper_input.beds_max
        self.baths_min = scraper_input.baths_min
        self.baths_max = scraper_input.baths_max
        self.sqft_min = scraper_input.sqft_min
        self.sqft_max = scraper_input.sqft_max
        self.price_min = scraper_input.price_min
        self.price_max = scraper_input.price_max
        self.lot_sqft_min = scraper_input.lot_sqft_min
        self.lot_sqft_max = scraper_input.lot_sqft_max
        self.year_built_min = scraper_input.year_built_min
        self.year_built_max = scraper_input.year_built_max

        # New sorting
        self.sort_by = scraper_input.sort_by
        self.sort_direction = scraper_input.sort_direction

        # Pagination control
        self.parallel = scraper_input.parallel

    def search(self) -> list[Union[Property | dict]]: ...

    @staticmethod
    def _parse_home(home) -> Property: ...

    def handle_location(self): ...

    @staticmethod
    def get_access_token():
        device_id = str(uuid.uuid4()).upper()

        # Use curl_cffi session for TLS fingerprinting if available
        if USE_CURL_CFFI:
            # Create a temporary session with TLS fingerprinting for this request
            impersonate_profile = get_random_impersonate()
            with requests.Session(impersonate=impersonate_profile) as session:
                response = session.post(
                    "https://graph.realtor.com/auth/token",
                    headers={
                        "Host": "graph.realtor.com",
                        "Accept": "*/*",
                        "Content-Type": "Application/json",
                        "X-Client-ID": "rdc_mobile_native,iphone",
                        "X-Visitor-ID": device_id,
                        "X-Client-Version": "24.21.23.679885",
                        "Accept-Language": "en-US,en;q=0.9",
                        "User-Agent": "Realtor.com/24.21.23.679885 CFNetwork/1494.0.7 Darwin/23.4.0",
                    },
                    data=json.dumps(
                        {
                            "grant_type": "device_mobile",
                            "device_id": device_id,
                            "client_app_id": "rdc_mobile_native,24.21.23.679885,iphone",
                        }
                    ),
                )
        else:
            response = requests.post(
                "https://graph.realtor.com/auth/token",
                headers={
                    "Host": "graph.realtor.com",
                    "Accept": "*/*",
                    "Content-Type": "Application/json",
                    "X-Client-ID": "rdc_mobile_native,iphone",
                    "X-Visitor-ID": device_id,
                    "X-Client-Version": "24.21.23.679885",
                    "Accept-Language": "en-US,en;q=0.9",
                    "User-Agent": "Realtor.com/24.21.23.679885 CFNetwork/1494.0.7 Darwin/23.4.0",
                },
                data=json.dumps(
                    {
                        "grant_type": "device_mobile",
                        "device_id": device_id,
                        "client_app_id": "rdc_mobile_native,24.21.23.679885,iphone",
                    }
                ),
            )

        data = response.json()

        if not (access_token := data.get("access_token")):
            raise AuthenticationError(
                "Failed to get access token, use a proxy/vpn or wait a moment and try again.", response=response
            )

        return access_token
