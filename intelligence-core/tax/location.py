"""
Tax Rate Calculator for SSIP

Auto-detects user location via IP and applies appropriate sales tax.
Uses free APIs for IP geolocation and maintains a database of US state tax rates.
"""

import os
import asyncio
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta

import httpx


# =============================================================================
# US State Sales Tax Rates (2024 averages including local taxes)
# Source: Tax Foundation and state revenue departments
# =============================================================================

US_STATE_TAX_RATES = {
    # State: (state_rate, avg_local_rate, combined_rate)
    "AL": (4.0, 5.24, 9.24),
    "AK": (0.0, 1.76, 1.76),
    "AZ": (5.6, 2.80, 8.40),
    "AR": (6.5, 2.97, 9.47),
    "CA": (7.25, 1.60, 8.85),
    "CO": (2.9, 4.87, 7.77),
    "CT": (6.35, 0.0, 6.35),
    "DE": (0.0, 0.0, 0.0),  # No sales tax
    "FL": (6.0, 1.05, 7.05),
    "GA": (4.0, 3.38, 7.38),
    "HI": (4.0, 0.50, 4.50),
    "ID": (6.0, 0.02, 6.02),
    "IL": (6.25, 2.57, 8.82),
    "IN": (7.0, 0.0, 7.0),
    "IA": (6.0, 0.94, 6.94),
    "KS": (6.5, 2.20, 8.70),
    "KY": (6.0, 0.0, 6.0),
    "LA": (4.45, 5.10, 9.55),
    "ME": (5.5, 0.0, 5.5),
    "MD": (6.0, 0.0, 6.0),
    "MA": (6.25, 0.0, 6.25),
    "MI": (6.0, 0.0, 6.0),
    "MN": (6.875, 0.63, 7.505),
    "MS": (7.0, 0.07, 7.07),
    "MO": (4.225, 4.06, 8.285),
    "MT": (0.0, 0.0, 0.0),  # No sales tax
    "NE": (5.5, 1.44, 6.94),
    "NV": (6.85, 1.38, 8.23),
    "NH": (0.0, 0.0, 0.0),  # No sales tax
    "NJ": (6.625, 0.0, 6.625),
    "NM": (4.875, 2.72, 7.595),
    "NY": (4.0, 4.52, 8.52),
    "NC": (4.75, 2.23, 6.98),
    "ND": (5.0, 2.04, 7.04),
    "OH": (5.75, 1.48, 7.23),
    "OK": (4.5, 4.47, 8.97),
    "OR": (0.0, 0.0, 0.0),  # No sales tax
    "PA": (6.0, 0.34, 6.34),
    "RI": (7.0, 0.0, 7.0),
    "SC": (6.0, 1.44, 7.44),
    "SD": (4.2, 1.90, 6.10),
    "TN": (7.0, 2.55, 9.55),
    "TX": (6.25, 1.95, 8.20),
    "UT": (6.1, 1.09, 7.19),
    "VT": (6.0, 0.24, 6.24),
    "VA": (5.3, 0.45, 5.75),
    "WA": (6.5, 2.73, 9.23),
    "WV": (6.0, 0.52, 6.52),
    "WI": (5.0, 0.44, 5.44),
    "WY": (4.0, 1.36, 5.36),
    "DC": (6.0, 0.0, 6.0),
}

# Default tax rate when location cannot be determined
DEFAULT_TAX_RATE = 7.0  # Approximate US average


@dataclass
class LocationInfo:
    """User location information from IP."""
    ip: str
    country: str
    country_code: str
    region: str  # State/Province code
    region_name: str  # Full state/province name
    city: str
    zip_code: str
    lat: float
    lon: float
    timezone: str
    detected_at: str


@dataclass
class TaxInfo:
    """Tax information for a location."""
    state_code: Optional[str]
    state_name: Optional[str]
    state_rate: float
    local_rate: float
    combined_rate: float
    is_tax_free: bool
    source: str  # "detected", "default", "manual"


class TaxCalculator:
    """
    Calculate sales tax based on user location.
    
    Uses IP geolocation to detect state and applies appropriate tax rate.
    Caches location to avoid repeated API calls.
    """
    
    # Free IP geolocation APIs (no API key required)
    IP_API_URL = "http://ip-api.com/json/{ip}?fields=status,country,countryCode,region,regionName,city,zip,lat,lon,timezone,query"
    IPINFO_URL = "https://ipinfo.io/{ip}/json"
    
    def __init__(self, cache_ttl_hours: int = 24):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self._location_cache: dict[str, tuple[LocationInfo, datetime]] = {}
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def detect_location(self, client_ip: Optional[str] = None) -> Optional[LocationInfo]:
        """
        Detect user location from IP address.
        
        Args:
            client_ip: Client IP address (if None, uses the caller's public IP)
            
        Returns:
            LocationInfo or None if detection fails
        """
        ip = client_ip or ""  # Empty string = use caller's IP
        
        # Check cache
        if ip in self._location_cache:
            cached, cached_at = self._location_cache[ip]
            if datetime.now() - cached_at < self.cache_ttl:
                return cached
        
        client = await self._get_client()
        
        # Try ip-api.com first (free, no key needed)
        try:
            url = self.IP_API_URL.format(ip=ip) if ip else "http://ip-api.com/json/?fields=status,country,countryCode,region,regionName,city,zip,lat,lon,timezone,query"
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    location = LocationInfo(
                        ip=data.get("query", ip),
                        country=data.get("country", ""),
                        country_code=data.get("countryCode", ""),
                        region=data.get("region", ""),
                        region_name=data.get("regionName", ""),
                        city=data.get("city", ""),
                        zip_code=data.get("zip", ""),
                        lat=data.get("lat", 0.0),
                        lon=data.get("lon", 0.0),
                        timezone=data.get("timezone", ""),
                        detected_at=datetime.now().isoformat(),
                    )
                    
                    # Cache the result
                    self._location_cache[ip] = (location, datetime.now())
                    return location
                    
        except Exception:
            pass
        
        return None
    
    def get_tax_rate(self, state_code: Optional[str] = None) -> TaxInfo:
        """
        Get tax rate for a US state.
        
        Args:
            state_code: Two-letter state code (e.g., "CA", "NY")
            
        Returns:
            TaxInfo with applicable rates
        """
        if not state_code:
            return TaxInfo(
                state_code=None,
                state_name=None,
                state_rate=DEFAULT_TAX_RATE,
                local_rate=0.0,
                combined_rate=DEFAULT_TAX_RATE,
                is_tax_free=False,
                source="default",
            )
        
        state_code = state_code.upper().strip()
        
        if state_code in US_STATE_TAX_RATES:
            state_rate, local_rate, combined_rate = US_STATE_TAX_RATES[state_code]
            
            # Get state name
            state_names = {
                "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
                "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
                "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
                "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
                "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
                "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
                "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
                "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
                "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
                "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
                "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
                "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
                "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
            }
            
            return TaxInfo(
                state_code=state_code,
                state_name=state_names.get(state_code, state_code),
                state_rate=state_rate,
                local_rate=local_rate,
                combined_rate=combined_rate,
                is_tax_free=(combined_rate == 0),
                source="detected",
            )
        
        # Unknown state code
        return TaxInfo(
            state_code=state_code,
            state_name=None,
            state_rate=DEFAULT_TAX_RATE,
            local_rate=0.0,
            combined_rate=DEFAULT_TAX_RATE,
            is_tax_free=False,
            source="default",
        )
    
    async def get_tax_for_ip(self, client_ip: Optional[str] = None) -> TaxInfo:
        """
        Get tax rate based on IP address location.
        
        Args:
            client_ip: Client IP address
            
        Returns:
            TaxInfo with applicable rates
        """
        location = await self.detect_location(client_ip)
        
        if location and location.country_code == "US":
            return self.get_tax_rate(location.region)
        elif location and location.country_code:
            # Non-US location - no US sales tax applies
            return TaxInfo(
                state_code=None,
                state_name=f"{location.country} (International)",
                state_rate=0.0,
                local_rate=0.0,
                combined_rate=0.0,
                is_tax_free=True,
                source="detected",
            )
        
        # Fallback to default
        return self.get_tax_rate(None)


async def get_tax_rate_for_ip(client_ip: Optional[str] = None) -> float:
    """
    Convenience function to get combined tax rate for an IP.
    
    Returns tax rate as a decimal (e.g., 0.0825 for 8.25%).
    """
    async with TaxCalculator() as calc:
        tax_info = await calc.get_tax_for_ip(client_ip)
        return tax_info.combined_rate / 100  # Convert percentage to decimal
