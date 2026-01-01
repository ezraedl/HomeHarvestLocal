"""
Parsers for Propwire.com data processing

NOTE: Field mappings are placeholders and need to be updated based on
actual Propwire API response structure discovered through investigation.
"""

from datetime import datetime
from typing import Optional
from ..models import Address, Description, PropertyType


def parse_address(result: dict, search_type: str = "general_search") -> Address:
    """
    Parse address data from Propwire result.
    
    Args:
        result: Property data dictionary from Propwire API
        search_type: Type of search (for future use)
        
    Returns:
        Address object
    """
    # Propwire API structure: address is an object with address, city, state, zip
    address_obj = result.get("address", {})
    
    # Build full address line
    address_parts = []
    if address_obj.get("address"):
        address_parts.append(address_obj["address"])
    if address_obj.get("city"):
        address_parts.append(address_obj["city"])
    if address_obj.get("state"):
        address_parts.append(address_obj["state"])
    if address_obj.get("zip"):
        address_parts.append(address_obj["zip"])
    
    full_line = ", ".join(address_parts) if address_parts else None
    
    # Extract street from address field (e.g., "249 N Hamilton Ave")
    street = address_obj.get("address")
    
    return Address(
        full_line=full_line,
        street=street,
        unit=None,  # Propwire doesn't seem to have unit in the address object
        city=address_obj.get("city"),
        state=address_obj.get("state"),
        zip=address_obj.get("zip"),
        
        # Additional address fields (not available in Propwire response)
        street_direction=None,
        street_number=None,
        street_name=None,
        street_suffix=None,
    )


def parse_description(result: dict) -> Description | None:
    """
    Parse description data from Propwire result.
    
    Args:
        result: Property data dictionary from Propwire API
        
    Returns:
        Description object or None
    """
    if not result:
        return None

    # Propwire API structure: property_type is a string like "SFR" (Single Family Residence)
    property_type = result.get("property_type")
    style = None
    if property_type:
        # Map Propwire property types to PropertyType enum
        type_mapping = {
            "SFR": "SINGLE_FAMILY",
            "MFR": "MULTI_FAMILY",
            "CONDO": "CONDO",
            "TOWNHOME": "CONDO_TOWNHOME",
            "LAND": "LAND",
            "APARTMENT": "APARTMENT",
        }
        mapped_type = type_mapping.get(property_type.upper(), property_type.upper())
        if mapped_type in PropertyType.__members__:
            style = PropertyType.__getitem__(mapped_type)
    
    # Extract primary photo (Propwire uses mls_first_photo_url)
    primary_photo = result.get("mls_first_photo_url")
    
    # Extract bathrooms - Propwire has bathrooms as a number (may be decimal)
    bathrooms = result.get("bathrooms")
    baths_full = int(bathrooms) if bathrooms is not None else None
    baths_half = int((bathrooms - int(bathrooms)) * 2) if bathrooms and bathrooms != int(bathrooms) else None
    
    # Extract square footage - Propwire uses building_area_sf or living_area_sf
    sqft = result.get("building_area_sf") or result.get("living_area_sf")
    
    # Extract lot size - Propwire uses lot_size_sf
    lot_sqft = result.get("lot_size_sf")
    
    # Extract garage info from garage_details
    garage_details = result.get("garage_details", {})
    garage_type = garage_details.get("garage_type")
    garage = None
    if garage_type and garage_type != "Unknown":
        # Try to extract number of spaces if available
        garage = garage_type
    
    return Description(
        primary_photo=primary_photo,
        alt_photos=None,  # Propwire doesn't provide alt photos in search results
        style=style,
        beds=result.get("bedrooms"),
        baths_full=baths_full,
        baths_half=baths_half,
        sqft=sqft,
        lot_sqft=lot_sqft,
        sold_price=result.get("last_sold_price"),
        year_built=result.get("year_built"),
        garage=garage,
        stories=None,  # Propwire doesn't provide stories
        text=None,  # Propwire doesn't provide description text in search results
        
        # Additional description fields
        name=None,
        type=property_type,
    )


def parse_neighborhoods(result: dict) -> Optional[str]:
    """
    Parse neighborhoods from location data.
    
    Args:
        result: Property data dictionary from Propwire API
        
    Returns:
        Comma-separated string of neighborhood names or None
    """
    # TODO: Update based on actual Propwire structure
    neighborhoods_list = []
    neighborhoods = result.get("location", {}).get("neighborhoods", []) or result.get("neighborhoods", [])

    if neighborhoods:
        for neighborhood in neighborhoods:
            if isinstance(neighborhood, dict):
                name = neighborhood.get("name")
            else:
                name = neighborhood
            if name:
                neighborhoods_list.append(name)

    return ", ".join(neighborhoods_list) if neighborhoods_list else None


def calculate_days_on_mls(result: dict) -> Optional[int]:
    """
    Calculate days on MLS from result data.
    
    Args:
        result: Property data dictionary from Propwire API
        
    Returns:
        Number of days on MLS or None
    """
    # Propwire uses mls_list_date for listing date
    list_date_str = result.get("mls_list_date")
    list_date = None
    if list_date_str:
        try:
            list_date_str_clean = list_date_str.replace('Z', '+00:00') if isinstance(list_date_str, str) and list_date_str.endswith('Z') else list_date_str
            list_date = datetime.fromisoformat(list_date_str_clean).replace(tzinfo=None)
        except (ValueError, AttributeError):
            try:
                list_date = datetime.strptime(str(list_date_str).split("T")[0], "%Y-%m-%d") if "T" in str(list_date_str) else None
            except (ValueError, AttributeError):
                list_date = None

    # Propwire uses last_sold_date (format: "2025-10-09")
    last_sold_date_str = result.get("last_sold_date")
    last_sold_date = None
    if last_sold_date_str:
        try:
            last_sold_date = datetime.strptime(str(last_sold_date_str), "%Y-%m-%d")
        except ValueError:
            last_sold_date = None
    
    # Propwire also has days_on_market field directly
    days_on_market = result.get("days_on_market")
    if days_on_market is not None:
        return int(days_on_market)
    
    today = datetime.now()

    # Use mls_attom_last_status_date if available
    mls_status_date_str = result.get("mls_attom_last_status_date")
    if mls_status_date_str and not list_date:
        try:
            list_date = datetime.strptime(str(mls_status_date_str), "%Y-%m-%d")
        except ValueError:
            pass

    if list_date:
        mls_status = result.get("mls_attom_last_status", "").upper()
        if mls_status == "SOLD":
            if last_sold_date:
                days = (last_sold_date - list_date).days
                if days >= 0:
                    return days
        elif mls_status in ("ACTIVE", "FOR_SALE"):
            days = (today - list_date).days
            if days >= 0:
                return days

    return None


def process_alt_photos(photos_info: list) -> list[str] | None:
    """
    Process alternative photos from photos info.
    
    Args:
        photos_info: List of photo dictionaries or URLs
        
    Returns:
        List of photo URLs or None
    """
    if not photos_info:
        return None

    photo_urls = []
    for photo_info in photos_info:
        if isinstance(photo_info, dict):
            url = photo_info.get("url") or photo_info.get("href") or photo_info.get("src")
        else:
            url = photo_info
        
        if url:
            photo_urls.append(url)
    
    return photo_urls if photo_urls else None


def parse_dates(result: dict) -> dict:
    """
    Parse all date fields from Propwire result.
    
    Args:
        result: Property data dictionary from Propwire API
        
    Returns:
        Dictionary with parsed datetime objects
    """
    dates = {}
    
    # Propwire date fields
    date_fields = {
        "list_date": result.get("mls_list_date"),
        "last_sold_date": result.get("last_sold_date"),  # Format: "2025-10-09"
        "pending_date": None,  # Propwire doesn't provide pending_date
        "last_update_date": result.get("mls_attom_last_status_date"),
    }
    
    for field_name, date_value in date_fields.items():
        if date_value:
            try:
                if isinstance(date_value, datetime):
                    dates[field_name] = date_value.replace(tzinfo=None)
                elif isinstance(date_value, str):
                    # Propwire dates are in "YYYY-MM-DD" format
                    if "T" in date_value:
                        date_str_clean = date_value.replace('Z', '+00:00') if date_value.endswith('Z') else date_value
                        dates[field_name] = datetime.fromisoformat(date_str_clean).replace(tzinfo=None)
                    else:
                        # Simple date format "YYYY-MM-DD"
                        dates[field_name] = datetime.strptime(date_value, "%Y-%m-%d")
                else:
                    dates[field_name] = None
            except (ValueError, AttributeError):
                dates[field_name] = None
        else:
            dates[field_name] = None
    
    return dates

