"""
SMS Verification Utility

Integrates with SMS-Activate and 5sim APIs to handle phone verification
during account creation.

Usage:
    from sms_service import SMSService
    
    async with SMSService() as sms:
        number = await sms.get_number(service="google")
        # ... use number in signup flow ...
        code = await sms.wait_for_code(timeout=120)
"""

import os
import asyncio
import aiohttp
from typing import Optional, Literal
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class PhoneNumber:
    """Represents a virtual phone number."""
    number: str
    country: str
    activation_id: str
    provider: str
    expires_at: Optional[datetime] = None


class SMSActivateClient:
    """
    Client for SMS-Activate API (https://sms-activate.org)
    
    Supports 600+ services and 180+ countries.
    """
    
    BASE_URL = "https://api.sms-activate.org/stubs/handler_api.php"
    
    # Service codes for common platforms
    SERVICES = {
        "google": "go",
        "gmail": "go",
        "outlook": "ot",
        "microsoft": "ot",
        "yahoo": "ya",
        "facebook": "fb",
        "twitter": "tw",
        "instagram": "ig",
        "amazon": "am",
        "telegram": "tg",
    }
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SMS_ACTIVATE_API_KEY")
        if not self.api_key:
            raise ValueError("SMS_ACTIVATE_API_KEY not configured")
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()
    
    async def _request(self, action: str, **params) -> str:
        """Make API request."""
        params["api_key"] = self.api_key
        params["action"] = action
        
        async with self._session.get(self.BASE_URL, params=params) as resp:
            return await resp.text()
    
    async def get_balance(self) -> float:
        """Get account balance."""
        result = await self._request("getBalance")
        if result.startswith("ACCESS_BALANCE:"):
            return float(result.split(":")[1])
        raise Exception(f"Failed to get balance: {result}")
    
    async def get_number(
        self, 
        service: str = "google", 
        country: str = "0"  # 0 = Russia (cheapest), 1 = Ukraine, 12 = USA
    ) -> PhoneNumber:
        """
        Get a virtual phone number for SMS verification.
        
        Args:
            service: Service name (google, outlook, facebook, etc.)
            country: Country code (0=Russia, 12=USA, 117=Portugal, etc.)
        
        Returns:
            PhoneNumber object with the number and activation details.
        """
        service_code = self.SERVICES.get(service.lower(), service)
        
        result = await self._request(
            "getNumber",
            service=service_code,
            country=country
        )
        
        if result.startswith("ACCESS_NUMBER:"):
            parts = result.split(":")
            activation_id = parts[1]
            number = parts[2]
            
            return PhoneNumber(
                number=number,
                country=country,
                activation_id=activation_id,
                provider="sms-activate"
            )
        elif result == "NO_NUMBERS":
            raise Exception("No numbers available for this service/country")
        elif result == "NO_BALANCE":
            raise Exception("Insufficient balance")
        else:
            raise Exception(f"Failed to get number: {result}")
    
    async def get_code(self, activation_id: str) -> Optional[str]:
        """
        Check for received SMS code.
        
        Returns the code if received, None if still waiting.
        """
        result = await self._request("getStatus", id=activation_id)
        
        if result.startswith("STATUS_OK:"):
            return result.split(":")[1]
        elif result == "STATUS_WAIT_CODE":
            return None
        elif result == "STATUS_CANCEL":
            raise Exception("Activation was cancelled")
        else:
            logger.warning(f"Unexpected status: {result}")
            return None
    
    async def wait_for_code(
        self, 
        activation_id: str, 
        timeout: int = 120,
        poll_interval: int = 5
    ) -> str:
        """
        Wait for SMS code with timeout.
        
        Args:
            activation_id: The activation ID from get_number()
            timeout: Maximum seconds to wait
            poll_interval: Seconds between checks
        
        Returns:
            The verification code.
        
        Raises:
            TimeoutError if code not received within timeout.
        """
        elapsed = 0
        while elapsed < timeout:
            code = await self.get_code(activation_id)
            if code:
                logger.info(f"Received code: {code}")
                await self.set_status(activation_id, "done")
                return code
            
            logger.debug(f"Waiting for code... ({elapsed}/{timeout}s)")
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        # Timeout - cancel activation
        await self.set_status(activation_id, "cancel")
        raise TimeoutError(f"No code received within {timeout} seconds")
    
    async def set_status(
        self, 
        activation_id: str, 
        status: Literal["done", "cancel", "retry"]
    ):
        """
        Set activation status.
        
        Args:
            activation_id: The activation ID
            status: 
                - "done": Mark as complete (6)
                - "cancel": Cancel activation (8)  
                - "retry": Request new SMS (-1)
        """
        status_codes = {"done": 6, "cancel": 8, "retry": -1}
        code = status_codes.get(status, 6)
        
        await self._request("setStatus", id=activation_id, status=code)


class FiveSimClient:
    """
    Client for 5sim API (https://5sim.net)
    
    Alternative SMS verification provider.
    """
    
    BASE_URL = "https://5sim.net/v1"
    
    SERVICES = {
        "google": "google",
        "gmail": "google",
        "microsoft": "microsoft",
        "outlook": "microsoft",
        "amazon": "amazon",
        "facebook": "facebook",
        "twitter": "twitter",
        "instagram": "instagram",
        "telegram": "telegram",
    }
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FIVESIM_API_KEY")
        if not self.api_key:
            raise ValueError("FIVESIM_API_KEY not configured")
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        headers = {"Authorization": f"Bearer {self.api_key}"}
        self._session = aiohttp.ClientSession(headers=headers)
        return self
    
    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()
    
    async def get_balance(self) -> float:
        """Get account balance."""
        async with self._session.get(f"{self.BASE_URL}/user/profile") as resp:
            data = await resp.json()
            return data.get("balance", 0)
    
    async def get_number(
        self, 
        service: str = "google",
        country: str = "russia",  # Cheapest option
        operator: str = "any"
    ) -> PhoneNumber:
        """Get a virtual phone number."""
        service_code = self.SERVICES.get(service.lower(), service)
        
        url = f"{self.BASE_URL}/user/buy/activation/{country}/{operator}/{service_code}"
        
        async with self._session.get(url) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise Exception(f"Failed to get number: {error}")
            
            data = await resp.json()
            
            return PhoneNumber(
                number=data["phone"],
                country=data["country"],
                activation_id=str(data["id"]),
                provider="5sim",
            )
    
    async def get_code(self, activation_id: str) -> Optional[str]:
        """Check for received SMS code."""
        url = f"{self.BASE_URL}/user/check/{activation_id}"
        
        async with self._session.get(url) as resp:
            data = await resp.json()
            
            if data.get("sms"):
                # Return the first SMS code
                sms = data["sms"][0]
                return sms.get("code") or sms.get("text")
            
            return None
    
    async def wait_for_code(
        self, 
        activation_id: str, 
        timeout: int = 120,
        poll_interval: int = 5
    ) -> str:
        """Wait for SMS code with timeout."""
        elapsed = 0
        while elapsed < timeout:
            code = await self.get_code(activation_id)
            if code:
                logger.info(f"Received code: {code}")
                await self.finish(activation_id)
                return code
            
            logger.debug(f"Waiting for code... ({elapsed}/{timeout}s)")
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        await self.cancel(activation_id)
        raise TimeoutError(f"No code received within {timeout} seconds")
    
    async def finish(self, activation_id: str):
        """Mark activation as complete."""
        url = f"{self.BASE_URL}/user/finish/{activation_id}"
        await self._session.get(url)
    
    async def cancel(self, activation_id: str):
        """Cancel activation."""
        url = f"{self.BASE_URL}/user/cancel/{activation_id}"
        await self._session.get(url)


class SMSService:
    """
    Unified SMS service that tries multiple providers.
    
    Usage:
        async with SMSService() as sms:
            # Get a phone number
            phone = await sms.get_number(service="google", country="usa")
            print(f"Use this number: {phone.number}")
            
            # Wait for verification code
            code = await sms.wait_for_code(timeout=120)
            print(f"Verification code: {code}")
    """
    
    def __init__(self, preferred_provider: str = "sms-activate"):
        self.preferred_provider = preferred_provider
        self._provider = None
        self._current_phone: Optional[PhoneNumber] = None
    
    async def __aenter__(self):
        # Try to initialize preferred provider
        try:
            if self.preferred_provider == "sms-activate":
                self._provider = SMSActivateClient()
            else:
                self._provider = FiveSimClient()
            
            await self._provider.__aenter__()
        except ValueError:
            # Try alternate provider
            try:
                if self.preferred_provider == "sms-activate":
                    self._provider = FiveSimClient()
                else:
                    self._provider = SMSActivateClient()
                
                await self._provider.__aenter__()
            except ValueError:
                raise ValueError("No SMS provider configured. Set SMS_ACTIVATE_API_KEY or FIVESIM_API_KEY")
        
        return self
    
    async def __aexit__(self, *args):
        if self._provider:
            await self._provider.__aexit__(*args)
    
    async def get_balance(self) -> float:
        """Get account balance."""
        return await self._provider.get_balance()
    
    async def get_number(
        self, 
        service: str = "google",
        country: str = "russia"
    ) -> PhoneNumber:
        """
        Get a phone number for verification.
        
        Args:
            service: Target service (google, outlook, facebook, etc.)
            country: Country for the phone number
        
        Returns:
            PhoneNumber object
        """
        # Map country names to provider-specific codes
        country_map = {
            "usa": ("12", "usa"),
            "uk": ("16", "england"),
            "russia": ("0", "russia"),
            "ukraine": ("1", "ukraine"),
            "germany": ("43", "germany"),
        }
        
        if isinstance(self._provider, SMSActivateClient):
            country_code = country_map.get(country.lower(), (country, country))[0]
        else:
            country_code = country_map.get(country.lower(), (country, country))[1]
        
        self._current_phone = await self._provider.get_number(service, country_code)
        return self._current_phone
    
    async def wait_for_code(self, timeout: int = 120) -> str:
        """Wait for verification code on the current number."""
        if not self._current_phone:
            raise ValueError("No phone number acquired. Call get_number() first.")
        
        return await self._provider.wait_for_code(
            self._current_phone.activation_id, 
            timeout
        )


# =============================================================================
# Example Usage
# =============================================================================

async def example():
    """Example usage of SMS service."""
    async with SMSService() as sms:
        # Check balance
        balance = await sms.get_balance()
        print(f"Balance: ${balance:.2f}")
        
        # Get a number for Google verification
        phone = await sms.get_number(service="google", country="russia")
        print(f"Phone number: +{phone.number}")
        print(f"Activation ID: {phone.activation_id}")
        
        # Wait for user to trigger SMS...
        print("Waiting for SMS code...")
        
        try:
            code = await sms.wait_for_code(timeout=120)
            print(f"Received code: {code}")
        except TimeoutError:
            print("No code received within timeout")


if __name__ == "__main__":
    asyncio.run(example())
