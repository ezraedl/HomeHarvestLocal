# Propwire API Response Structure

## Overview
This document describes the actual API response structure captured from the browser for the Propwire property search API.

## Property Search API Response

### Endpoint
`POST https://api.propwire.com/api/property_search`

### Request Format
```json
{
  "size": 250,
  "result_index": 0,
  "house": true,
  "locations": [
    {
      "searchType": "Z",
      "zip": "46201",
      "state": "IN",
      "title": "46201, IN"
    }
  ]
}
```

### Response Structure
```json
{
  "request": {...},
  "response": [
    {
      // Property object (see below)
    }
  ],
  "result_count": 14875,
  "result_index": 0,
  "result_index_end": 250,
  "record_count": 250,
  "lead_type_counts": {...},
  "status_code": 200,
  "status_message": "Success",
  "request_execution_time_MS": 123
}
```

## Property Object Structure

### Core Fields
- `id`: Property ID (integer, e.g., 61752)
- `address`: Address object
  - `address`: Street address (e.g., "249 N Hamilton Ave")
  - `city`: City name (e.g., "Indianapolis")
  - `state`: State code (e.g., "IN")
  - `zip`: ZIP code (e.g., "46201")

### Property Details
- `bedrooms`: Number of bedrooms (integer)
- `bathrooms`: Number of bathrooms (number, may be decimal)
- `building_area_sf`: Building square footage (integer)
- `living_area_sf`: Living area square footage (integer)
- `lot_size_sf`: Lot size in square feet (integer)
- `lot_size_acres`: Lot size in acres (string, e.g., "0.1134068")
- `property_type`: Property type code (e.g., "SFR" = Single Family Residence)
- `year_built`: Year built (integer, e.g., 1955)

### Financial Information
- `estimated_value`: Estimated property value (integer)
- `estimated_equity`: Estimated equity amount (integer)
- `estimated_equity_percentage`: Equity percentage (integer, can be negative)
- `estimated_ltv`: Estimated loan-to-value ratio (string)
- `estimated_price_per_sf`: Price per square foot (string)
- `estimated_zip_price_per_sf`: ZIP average price per square foot (string)
- `last_sold_date`: Last sold date (string, format: "YYYY-MM-DD")
- `last_sold_price`: Last sold price (integer)

### MLS Information
- `mls_attom_last_status`: MLS status (e.g., "ACTIVE", "SOLD", "PENDING")
- `mls_attom_last_status_date`: Last status change date (string, format: "YYYY-MM-DD")
- `mls_attom_price`: MLS list price (integer)
- `mls_list_date`: MLS list date (string or null)
- `mls_list_price`: MLS list price (integer or null)
- `mls_list_price_per_sf`: MLS price per square foot (number or null)
- `mls_sold_date`: MLS sold date (string or null)
- `mls_sold_price`: MLS sold price (integer or null)
- `mls_sold_price_per_sf`: MLS sold price per square foot (number or null)
- `mls_first_photo_url`: First photo URL (string or null)
- `days_on_market`: Days on market (integer or null)

### Ownership Information
- `owner_name`: Array of owner names (e.g., ["TCN 2 HOLDINGS LLC"])
- `owner_mailing_address`: Owner mailing address object
  - `owners_mailing_address`: Street address
  - `owners_mailing_city`: City
  - `owners_mailing_state`: State
  - `owners_mailing_zip`: ZIP code
  - `owners_mailing_zip4`: ZIP+4 (string or null)
  - `owners_mail_privacy`: Privacy flag (string or null)
- `owner_occupied`: Owner occupied flag (boolean)
- `company_owned`: Company owned flag (boolean)
- `individual_owned`: Individual owned flag (boolean)
- `trust_owned`: Trust owned flag (boolean or null)
- `government_owned`: Government owned flag (boolean or null)
- `investor_owned`: Investor owned flag (boolean or null)
- `months_of_ownership`: Months of ownership (integer)
- `years_of_ownership`: Years of ownership (integer)

### Location Information
- `geo_location`: Geographic location object
  - `latitude`: Latitude (string, e.g., "39.77105")
  - `longitude`: Longitude (string, e.g., "-86.125102")

### Property Features
- `basement_details`: Basement details object
  - `basement_finished_percentage`: Finished percentage (integer or null)
  - `basement_sf`: Basement square footage (integer)
  - `basement_sf_finished`: Finished basement SF (integer or null)
  - `basement_sf_unfinished`: Unfinished basement SF (integer or null)
  - `basement_type`: Basement type (e.g., "FINISHED", "Unknown")
- `garage_details`: Garage details object
  - `garage_area_sf`: Garage square footage (integer)
  - `garage_area_sf_finished`: Finished garage SF (integer or null)
  - `garage_area_sf_unfinished`: Unfinished garage SF (integer or null)
  - `garage_type`: Garage type (e.g., "Unknown")
- `cooling_type`: Cooling type (string, e.g., "Unknown")
- `heating_type`: Heating type (string, e.g., "Central")
- `heating_fuel`: Heating fuel (string, e.g., "Unknown")
- `fireplace`: Fireplace flag (boolean or null)
- `fireplace_type`: Fireplace type (string, e.g., "Unknown")
- `fireplace_count`: Number of fireplaces (integer)
- `pool`: Pool flag (string, e.g., "Unknown")
- `pool_area_sf`: Pool area square footage (integer)
- `pool_type`: Pool type (string, e.g., "Unknown")
- `units`: Number of units (integer, 0 for single family)

### Tax Information
- `tax_assessed_values`: Tax assessed values object
  - `year_assessed`: Assessment year (integer, e.g., 2024)
  - `total`: Total assessed value (integer)
  - `improvements`: Improvements value (integer)
  - `land`: Land value (integer)
  - `improvements_percentage`: Improvements percentage (integer)
  - `previous_total`: Previous total (integer)

### Lead Type Flags
- `lead_type`: Object with boolean flags for various lead types
  - `absentee_owner`: Absentee owner flag
  - `adjustable_loan`: Adjustable loan flag
  - `assumable_loan`: Assumable loan flag
  - `auction`: Auction flag (boolean or null)
  - `bank_owned`: Bank owned flag
  - `cash_buyer`: Cash buyer flag
  - `empty_nester`: Empty nester flag (boolean or null)
  - `flipped_property`: Flipped property flag
  - `free_and_clear`: Free and clear flag
  - `high_equity`: High equity flag
  - `low_equity`: Low equity flag
  - `negative_equity`: Negative equity flag
  - `intrafamily_transfer`: Intrafamily transfer flag
  - `mls_active`: MLS active flag
  - `mls_pending`: MLS pending flag
  - `mls_failed`: MLS failed flag
  - `mls_sold`: MLS sold flag
  - `out_of_state_owner`: Out of state owner flag
  - `preforeclosure`: Preforeclosure flag (boolean or null)
  - `preprobate`: Preprobate flag
  - `private_lender`: Private lender flag
  - `tired_landlord`: Tired landlord flag
  - `vacant_home`: Vacant home flag
  - `vacant_lot`: Vacant lot flag
  - `zombie_property`: Zombie property flag
  - `code_violation`: Code violation flag
  - `lien_tax`: Tax lien flag
  - `lien_misc`: Miscellaneous lien flag
  - `divorce`: Divorce flag
  - `bankruptcy`: Bankruptcy flag
  - `abandoned_homes`: Abandoned homes flag
  - `tax_dodgers`: Tax dodgers flag
  - `ultra_liens`: Ultra liens flag
  - `ultra_violations`: Ultra violations flag
  - `bargain_properties`: Bargain properties flag
  - `desperate_landlords`: Desperate landlords flag
  - `cash_flow_rentals`: Cash flow rentals flag
  - `creative_financing`: Creative financing flag
  - `hidden_gems_mls`: Hidden gems MLS flag
  - `sub_to_mls`: Sub to MLS flag
  - `sub_to_off_market`: Sub to off market flag

### Other Fields
- `foreclosure`: Foreclosure information (null in sample)
- `auction_date`: Auction date (string or null)
- `auction_time`: Auction time (string or null)
- `listing_key`: Listing key (string or null)
- `listhub`: Listhub information (null in sample)

## Field Mappings to Property Model

### Address
- `address.address` → `Address.street`
- `address.city` → `Address.city`
- `address.state` → `Address.state`
- `address.zip` → `Address.zip`

### Description
- `bedrooms` → `Description.beds`
- `bathrooms` → `Description.baths_full` (integer part) and `Description.baths_half` (decimal part)
- `building_area_sf` or `living_area_sf` → `Description.sqft`
- `lot_size_sf` → `Description.lot_sqft`
- `property_type` → `Description.style` (mapped to PropertyType enum)
- `year_built` → `Description.year_built`
- `mls_first_photo_url` → `Description.primary_photo`
- `garage_details.garage_type` → `Description.garage`

### Property
- `id` → `Property.property_id` and `Property.listing_id`
- `mls_attom_last_status` → `Property.status` (mapped)
- `mls_list_price` or `mls_attom_price` → `Property.list_price`
- `estimated_price_per_sf` → `Property.prc_sqft`
- `mls_list_date` → `Property.list_date`
- `last_sold_date` → `Property.last_sold_date`
- `last_sold_price` → `Property.last_sold_price`
- `mls_attom_last_status_date` → `Property.last_update_date`
- `geo_location.latitude` → `Property.latitude` (converted to float)
- `geo_location.longitude` → `Property.longitude` (converted to float)
- `estimated_value` → `Property.estimated_value`
- `tax_assessed_values.total` → `Property.assessed_value`
- `days_on_market` → `Property.days_on_mls`
- `lead_type.mls_active` → Used to determine `Property.status`
- `lead_type.mls_pending` → Used to determine `Property.status`
- `lead_type.mls_sold` → Used to determine `Property.status`

## Notes

1. **Pagination**: Uses `result_index` (0-indexed) and `size` instead of `page` and `limit`
2. **Response Array**: Properties are in `response` array, not `data`
3. **Total Count**: Use `result_count` for total number of results
4. **Status Mapping**: Use `lead_type` flags and `mls_attom_last_status` to determine property status
5. **Coordinates**: Latitude/longitude are strings and need to be converted to floats
6. **Dates**: Dates are in "YYYY-MM-DD" format (no time component)
7. **Property Type**: "SFR" maps to "SINGLE_FAMILY" in PropertyType enum

## Updated Files

1. `parsers.py` - Updated with actual field mappings
2. `processors.py` - Updated with actual field mappings
3. `queries.py` - Updated `build_search_request` to use `size` and `result_index`
4. `__init__.py` - Updated `general_search` to handle `response` array



