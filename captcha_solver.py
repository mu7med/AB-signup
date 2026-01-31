"""
CAPTCHA Solver Utility

Integrates with CapSolver and 2Captcha APIs to handle CAPTCHAs
during account creation.

Usage:
    from captcha_solver import CaptchaSolver
    
    async with CaptchaSolver() as solver:
        token = await solver.solve_recaptcha(
            site_key="6Le-xxx",
            url="https://example.com/signup"
        )
"""

import os
import asyncio
import aiohttp
from typing import Optional, Literal
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class CaptchaSolution:
    """Represents a solved CAPTCHA."""
    token: str
    task_id: str
    provider: str
    cost: float = 0.0


class CapSolverClient:
    """
    Client for CapSolver API (https://capsolver.com)
    
    Supports: reCAPTCHA v2/v3, hCaptcha, FunCaptcha, Cloudflare, etc.
    """
    
    BASE_URL = "https://api.capsolver.com"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("CAPSOLVER_API_KEY")
        if not self.api_key:
            raise ValueError("CAPSOLVER_API_KEY not configured")
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()
    
    async def get_balance(self) -> float:
        """Get account balance."""
        async with self._session.post(
            f"{self.BASE_URL}/getBalance",
            json={"clientKey": self.api_key}
        ) as resp:
            data = await resp.json()
            if data.get("errorId") == 0:
                return data.get("balance", 0)
            raise Exception(f"Failed to get balance: {data}")
    
    async def solve_recaptcha_v2(
        self,
        site_key: str,
        url: str,
        invisible: bool = False,
        enterprise: bool = False,
    ) -> CaptchaSolution:
        """
        Solve reCAPTCHA v2.
        
        Args:
            site_key: The reCAPTCHA site key (data-sitekey attribute)
            url: The page URL where CAPTCHA appears
            invisible: Whether it's invisible reCAPTCHA
            enterprise: Whether it's reCAPTCHA Enterprise
        
        Returns:
            CaptchaSolution with the token to submit
        """
        if enterprise:
            task_type = "ReCaptchaV2EnterpriseTaskProxyLess"
        else:
            task_type = "ReCaptchaV2TaskProxyLess"
        
        task = {
            "type": task_type,
            "websiteURL": url,
            "websiteKey": site_key,
        }
        
        if invisible:
            task["isInvisible"] = True
        
        return await self._create_and_wait(task)
    
    async def solve_recaptcha_v3(
        self,
        site_key: str,
        url: str,
        action: str = "submit",
        min_score: float = 0.7,
    ) -> CaptchaSolution:
        """
        Solve reCAPTCHA v3.
        
        Args:
            site_key: The reCAPTCHA site key
            url: The page URL
            action: The action parameter
            min_score: Minimum required score (0.1 to 0.9)
        """
        task = {
            "type": "ReCaptchaV3TaskProxyLess",
            "websiteURL": url,
            "websiteKey": site_key,
            "pageAction": action,
            "minScore": min_score,
        }
        
        return await self._create_and_wait(task)
    
    async def solve_hcaptcha(
        self,
        site_key: str,
        url: str,
        enterprise: bool = False,
    ) -> CaptchaSolution:
        """Solve hCaptcha."""
        task_type = "HCaptchaEnterpriseTaskProxyLess" if enterprise else "HCaptchaTurboTaskProxyLess"
        
        task = {
            "type": task_type,
            "websiteURL": url,
            "websiteKey": site_key,
        }
        
        return await self._create_and_wait(task)
    
    async def solve_funcaptcha(
        self,
        public_key: str,
        url: str,
        subdomain: Optional[str] = None,
    ) -> CaptchaSolution:
        """Solve FunCaptcha (Arkose Labs)."""
        task = {
            "type": "FunCaptchaTaskProxyLess",
            "websiteURL": url,
            "websitePublicKey": public_key,
        }
        
        if subdomain:
            task["funcaptchaApiJSSubdomain"] = subdomain
        
        return await self._create_and_wait(task)
    
    async def solve_turnstile(
        self,
        site_key: str,
        url: str,
    ) -> CaptchaSolution:
        """Solve Cloudflare Turnstile."""
        task = {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteURL": url,
            "websiteKey": site_key,
        }
        
        return await self._create_and_wait(task)
    
    async def _create_and_wait(
        self, 
        task: dict, 
        timeout: int = 120
    ) -> CaptchaSolution:
        """Create task and wait for solution."""
        # Create task
        async with self._session.post(
            f"{self.BASE_URL}/createTask",
            json={
                "clientKey": self.api_key,
                "task": task
            }
        ) as resp:
            data = await resp.json()
            
            if data.get("errorId") != 0:
                raise Exception(f"Failed to create task: {data.get('errorDescription')}")
            
            task_id = data.get("taskId")
            
            # Check if solved immediately (some tasks)
            if data.get("solution"):
                return CaptchaSolution(
                    token=data["solution"].get("gRecaptchaResponse") or data["solution"].get("token"),
                    task_id=task_id,
                    provider="capsolver",
                )
        
        # Poll for result
        elapsed = 0
        poll_interval = 3
        
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            
            async with self._session.post(
                f"{self.BASE_URL}/getTaskResult",
                json={
                    "clientKey": self.api_key,
                    "taskId": task_id
                }
            ) as resp:
                data = await resp.json()
                
                if data.get("errorId") != 0:
                    raise Exception(f"Task failed: {data.get('errorDescription')}")
                
                if data.get("status") == "ready":
                    solution = data.get("solution", {})
                    token = (
                        solution.get("gRecaptchaResponse") or 
                        solution.get("token") or
                        solution.get("text")
                    )
                    
                    return CaptchaSolution(
                        token=token,
                        task_id=task_id,
                        provider="capsolver",
                        cost=data.get("cost", 0),
                    )
                
                logger.debug(f"Waiting for solution... ({elapsed}/{timeout}s)")
        
        raise TimeoutError(f"CAPTCHA not solved within {timeout} seconds")


class TwoCaptchaClient:
    """
    Client for 2Captcha API (https://2captcha.com)
    
    Alternative CAPTCHA solving provider.
    """
    
    BASE_URL = "https://2captcha.com"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TWO_CAPTCHA_API_KEY")
        if not self.api_key:
            raise ValueError("TWO_CAPTCHA_API_KEY not configured")
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()
    
    async def get_balance(self) -> float:
        """Get account balance."""
        url = f"{self.BASE_URL}/res.php"
        params = {
            "key": self.api_key,
            "action": "getbalance",
            "json": 1
        }
        
        async with self._session.get(url, params=params) as resp:
            data = await resp.json()
            if data.get("status") == 1:
                return float(data.get("request", 0))
            raise Exception(f"Failed to get balance: {data}")
    
    async def solve_recaptcha_v2(
        self,
        site_key: str,
        url: str,
        invisible: bool = False,
    ) -> CaptchaSolution:
        """Solve reCAPTCHA v2."""
        params = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": url,
            "json": 1,
        }
        
        if invisible:
            params["invisible"] = 1
        
        return await self._create_and_wait(params)
    
    async def solve_recaptcha_v3(
        self,
        site_key: str,
        url: str,
        action: str = "submit",
        min_score: float = 0.7,
    ) -> CaptchaSolution:
        """Solve reCAPTCHA v3."""
        params = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": url,
            "version": "v3",
            "action": action,
            "min_score": min_score,
            "json": 1,
        }
        
        return await self._create_and_wait(params)
    
    async def solve_hcaptcha(
        self,
        site_key: str,
        url: str,
    ) -> CaptchaSolution:
        """Solve hCaptcha."""
        params = {
            "key": self.api_key,
            "method": "hcaptcha",
            "sitekey": site_key,
            "pageurl": url,
            "json": 1,
        }
        
        return await self._create_and_wait(params)
    
    async def _create_and_wait(
        self, 
        params: dict, 
        timeout: int = 120
    ) -> CaptchaSolution:
        """Create task and wait for solution."""
        # Submit task
        async with self._session.get(
            f"{self.BASE_URL}/in.php",
            params=params
        ) as resp:
            data = await resp.json()
            
            if data.get("status") != 1:
                raise Exception(f"Failed to create task: {data.get('request')}")
            
            task_id = data.get("request")
        
        # Poll for result
        elapsed = 0
        poll_interval = 5
        
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            
            async with self._session.get(
                f"{self.BASE_URL}/res.php",
                params={
                    "key": self.api_key,
                    "action": "get",
                    "id": task_id,
                    "json": 1
                }
            ) as resp:
                data = await resp.json()
                
                if data.get("status") == 1:
                    return CaptchaSolution(
                        token=data.get("request"),
                        task_id=task_id,
                        provider="2captcha",
                    )
                elif data.get("request") != "CAPCHA_NOT_READY":
                    raise Exception(f"Task failed: {data.get('request')}")
                
                logger.debug(f"Waiting for solution... ({elapsed}/{timeout}s)")
        
        raise TimeoutError(f"CAPTCHA not solved within {timeout} seconds")


class CaptchaSolver:
    """
    Unified CAPTCHA solver that tries multiple providers.
    
    Usage:
        async with CaptchaSolver() as solver:
            # Solve reCAPTCHA v2
            solution = await solver.solve_recaptcha_v2(
                site_key="6Le-xxx",
                url="https://example.com/signup"
            )
            print(f"Token: {solution.token}")
    """
    
    def __init__(self, preferred_provider: str = "capsolver"):
        self.preferred_provider = preferred_provider
        self._provider = None
    
    async def __aenter__(self):
        # Try to initialize preferred provider
        try:
            if self.preferred_provider == "capsolver":
                self._provider = CapSolverClient()
            else:
                self._provider = TwoCaptchaClient()
            
            await self._provider.__aenter__()
        except ValueError:
            # Try alternate provider
            try:
                if self.preferred_provider == "capsolver":
                    self._provider = TwoCaptchaClient()
                else:
                    self._provider = CapSolverClient()
                
                await self._provider.__aenter__()
            except ValueError:
                raise ValueError("No CAPTCHA solver configured. Set CAPSOLVER_API_KEY or TWO_CAPTCHA_API_KEY")
        
        return self
    
    async def __aexit__(self, *args):
        if self._provider:
            await self._provider.__aexit__(*args)
    
    async def get_balance(self) -> float:
        """Get account balance."""
        return await self._provider.get_balance()
    
    async def solve_recaptcha_v2(
        self,
        site_key: str,
        url: str,
        invisible: bool = False,
    ) -> CaptchaSolution:
        """Solve reCAPTCHA v2."""
        logger.info(f"Solving reCAPTCHA v2 for {url}...")
        solution = await self._provider.solve_recaptcha_v2(site_key, url, invisible)
        logger.info(f"Solved! Cost: ${solution.cost:.4f}")
        return solution
    
    async def solve_recaptcha_v3(
        self,
        site_key: str,
        url: str,
        action: str = "submit",
        min_score: float = 0.7,
    ) -> CaptchaSolution:
        """Solve reCAPTCHA v3."""
        logger.info(f"Solving reCAPTCHA v3 for {url}...")
        solution = await self._provider.solve_recaptcha_v3(site_key, url, action, min_score)
        logger.info(f"Solved! Cost: ${solution.cost:.4f}")
        return solution
    
    async def solve_hcaptcha(
        self,
        site_key: str,
        url: str,
    ) -> CaptchaSolution:
        """Solve hCaptcha."""
        logger.info(f"Solving hCaptcha for {url}...")
        
        if isinstance(self._provider, CapSolverClient):
            solution = await self._provider.solve_hcaptcha(site_key, url)
        else:
            solution = await self._provider.solve_hcaptcha(site_key, url)
        
        logger.info(f"Solved! Cost: ${solution.cost:.4f}")
        return solution
    
    async def solve_turnstile(
        self,
        site_key: str,
        url: str,
    ) -> CaptchaSolution:
        """Solve Cloudflare Turnstile."""
        if not isinstance(self._provider, CapSolverClient):
            raise NotImplementedError("Turnstile solving requires CapSolver")
        
        logger.info(f"Solving Cloudflare Turnstile for {url}...")
        solution = await self._provider.solve_turnstile(site_key, url)
        logger.info(f"Solved!")
        return solution


# =============================================================================
# Example Usage
# =============================================================================

async def example():
    """Example usage of CAPTCHA solver."""
    async with CaptchaSolver() as solver:
        # Check balance
        balance = await solver.get_balance()
        print(f"Balance: ${balance:.2f}")
        
        # Solve a reCAPTCHA v2
        solution = await solver.solve_recaptcha_v2(
            site_key="6Le-wvkSAAAAAPBMRTvw0Q4Muexq9bi0DJwx_mJ-",  # Demo site key
            url="https://www.google.com/recaptcha/api2/demo"
        )
        print(f"Token: {solution.token[:50]}...")


if __name__ == "__main__":
    asyncio.run(example())
