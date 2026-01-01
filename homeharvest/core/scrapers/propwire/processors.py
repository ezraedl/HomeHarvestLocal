"""
Processors for Propwire.com property data processing

NOTE: Field mappings are placeholders and need to be updated based on
actual Propwire API response structure discovered through investigation.
"""

from datetime import datetime
from typing import Optional
from ..models import (
    Property,
    ListingType,
    Agent,
    Broker,
    Builder,
    Advertisers,
    Office,
    ReturnType
)
from .parsers import (
    parse_neighborhoods,
    parse_address,
    parse_description,
    calculate_days_on_mls,
    parse_dates,
)


def process_advertisers(advertisers: list[dict] | None) -> Advertisers | None:
    """
    Process advertisers data from Propwire API response.
    
    Args:
        advertisers: List of advertiser dictionaries from Propwire
        
    Returns:
        Advertisers object or None
    """
    if not advertisers:
        return None

    processed_advertisers = Advertisers()

    for advertiser in advertisers:
        # TODO: Update field mappings based on actual Propwire structure
        advertiser_type = advertiser.get("type") or advertiser.get("role")
        
        # Process agent/seller information
        if advertiser_type in ("seller", "agent", "listing_agent"):
            processed_advertisers.agent = Agent(
                uuid=advertiser.get("id") or advertiser.get("uuid"),
                nrds_id=advertiser.get("nrds_id"),
                mls_set=advertiser.get("mls_set"),
                name=advertiser.get("name") or advertiser.get("agent_name"),
                email=advertiser.get("email"),
                phones=advertiser.get("phones") or advertiser.get("phone"),
                state_license=advertiser.get("state_license") or advertiser.get("license"),
            )

            # Process broker information
            broker_data = advertiser.get("broker") or advertiser.get("brokerage")
            if broker_data and isinstance(broker_data, dict):
                if broker_data.get("name"):
                    processed_advertisers.broker = Broker(
                        uuid=broker_data.get("id") or broker_data.get("uuid"),
                        name=broker_data.get("name"),
                    )

            # Process office information
            office_data = advertiser.get("office")
            if office_data and isinstance(office_data, dict):
                processed_advertisers.office = Office(
                    uuid=office_data.get("id") or office_data.get("uuid"),
                    mls_set=office_data.get("mls_set"),
                    name=office_data.get("name"),
                    email=office_data.get("email"),
                    phones=office_data.get("phones") or office_data.get("phone"),
                )

        # Process builder information
        if advertiser_type == "builder" or advertiser.get("builder"):
            builder_data = advertiser.get("builder") or advertiser
            processed_advertisers.builder = Builder(
                uuid=builder_data.get("id") or builder_data.get("uuid"),
                name=builder_data.get("name") or builder_data.get("builder_name"),
            )

    return processed_advertisers if processed_advertisers.agent or processed_advertisers.broker else None


def process_property(result: dict, mls_only: bool = False, extra_property_data: bool = False, 
                    exclude_pending: bool = False, listing_type: ListingType = ListingType.FOR_SALE,
                    get_key_func=None, process_extra_property_details_func=None) -> Property | None:
    """
    Process property data from Propwire API response.
    
    Args:
        result: Property data dictionary from Propwire API
        mls_only: Only return properties with MLS data
        extra_property_data: Fetch additional property details
        exclude_pending: Exclude pending/contingent properties
        listing_type: Type of listing to filter
        get_key_func: Function to safely get nested keys (for future use)
        process_extra_property_details_func: Function to process extra details
        
    Returns:
        Property object or None
    """
    # Propwire API structure: id is the property ID
    property_id = result.get("id")
    if not property_id:
        return None  # Must have property ID
    
    # Extract MLS information - Propwire uses mls_attom_last_status
    mls_status = result.get("mls_attom_last_status")
    mls = "MLS" if mls_status else None  # Propwire doesn't provide MLS ID, just status
    
    if not mls and mls_only:
        return None

    # Extract coordinates from geo_location object
    geo_location = result.get("geo_location", {})
    latitude = geo_location.get("latitude")
    longitude = geo_location.get("longitude")
    if latitude:
        latitude = float(latitude) if isinstance(latitude, str) else latitude
    if longitude:
        longitude = float(longitude) if isinstance(longitude, str) else longitude

    # Check for pending/contingent status using lead_type flags
    lead_type = result.get("lead_type", {})
    is_pending = lead_type.get("mls_pending", False)
    is_sold = lead_type.get("mls_sold", False)
    is_active = lead_type.get("mls_active", False)

    if is_pending and (exclude_pending and listing_type != ListingType.PENDING):
        return None

    # Process extra property details if requested
    prop_details = {}
    if extra_property_data and process_extra_property_details_func:
        prop_details = process_extra_property_details_func(result) or {}

    # Parse dates
    parsed_dates = parse_dates(result)

    # Process advertisers (Propwire doesn't provide advertiser info in search results)
    advertisers = None

    # Map status based on lead_type flags and mls_attom_last_status
    mapped_status = "OFF_MARKET"  # Default
    if is_active:
        mapped_status = "FOR_SALE"
    elif is_pending:
        mapped_status = "PENDING"
    elif is_sold:
        mapped_status = "SOLD"
    elif mls_status:
        # Use mls_attom_last_status as fallback
        status_mapping = {
            "ACTIVE": "FOR_SALE",
            "PENDING": "PENDING",
            "SOLD": "SOLD",
            "OFF_MARKET": "OFF_MARKET",
        }
        mapped_status = status_mapping.get(mls_status.upper(), "OFF_MARKET")

    # Extract list price - Propwire uses mls_attom_price or mls_list_price
    list_price = result.get("mls_list_price") or result.get("mls_attom_price")
    
    # Extract price per sqft - Propwire uses estimated_price_per_sf
    prc_sqft = result.get("estimated_price_per_sf")
    if prc_sqft:
        prc_sqft = float(prc_sqft) if isinstance(prc_sqft, str) else prc_sqft

    # Extract estimated value
    estimated_value = result.get("estimated_value")
    
    # Extract assessed value from tax_assessed_values
    tax_assessed = result.get("tax_assessed_values", {})
    assessed_value = tax_assessed.get("total") if tax_assessed else None

    # Create Property object
    property_obj = Property(
        mls=mls,
        mls_id=None,  # Propwire doesn't provide MLS ID
        property_url=None,  # Propwire doesn't provide property URL in search results
        property_id=str(property_id),
        listing_id=str(property_id),
        permalink=None,  # Propwire doesn't provide permalink
        status=mapped_status,
        list_price=list_price,
        list_price_min=None,  # Propwire doesn't provide price range
        list_price_max=None,
        list_date=parsed_dates.get("list_date"),
        prc_sqft=prc_sqft,
        last_sold_date=parsed_dates.get("last_sold_date"),
        pending_date=parsed_dates.get("pending_date"),
        last_status_change_date=parsed_dates.get("last_update_date"),
        last_update_date=parsed_dates.get("last_update_date"),
        new_construction=False,  # Propwire doesn't provide this
        hoa_fee=None,  # Propwire doesn't provide HOA fee
        latitude=latitude,
        longitude=longitude,
        address=parse_address(result),
        description=parse_description(result),
        neighborhoods=None,  # Propwire doesn't provide neighborhoods
        county=None,  # Propwire doesn't provide county in search results
        fips_code=None,  # Propwire doesn't provide FIPS code
        days_on_mls=calculate_days_on_mls(result),
        nearby_schools=prop_details.get("schools"),
        assessed_value=assessed_value,
        estimated_value=estimated_value,
        advertisers=advertisers,
        tax=prop_details.get("tax"),
        tax_history=prop_details.get("tax_history"),
        
        # Additional fields
        mls_status=mls_status,
        last_sold_price=result.get("last_sold_price"),
        tags=None,  # Propwire doesn't provide tags
        details=None,  # Propwire doesn't provide details
    )

    return property_obj


def process_extra_property_details(result: dict, get_key_func=None) -> dict:
    """
    Process extra property details from Propwire API response.
    
    Args:
        result: Property data dictionary from Propwire API
        get_key_func: Function to safely get nested keys (for future use)
        
    Returns:
        Dictionary with extra property details
    """
    # Propwire doesn't provide school information in search results
    schools = None
    
    # Extract tax information from tax_assessed_values
    tax_assessed = result.get("tax_assessed_values", {})
    assessed_value = tax_assessed.get("total") if tax_assessed else None
    
    # Build tax history from tax_assessed_values
    tax_history = None
    if tax_assessed:
        tax_history = [{
            "year": tax_assessed.get("year_assessed"),
            "assessed_value": tax_assessed.get("total"),
            "land": tax_assessed.get("land"),
            "improvements": tax_assessed.get("improvements"),
        }]
    
    return {
        "schools": schools,
        "assessed_value": assessed_value,
        "tax": None,  # Propwire doesn't provide tax amount
        "tax_history": tax_history,
    }


def get_key(data: dict, keys: list):
    """
    Get nested key from dictionary safely.
    
    Args:
        data: Dictionary to search
        keys: List of keys to traverse
        
    Returns:
        Value at nested key or empty dict
    """
    try:
        value = data
        for key in keys:
            value = value[key]
        return value or {}
    except (KeyError, TypeError, IndexError):
        return {}

