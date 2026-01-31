"""
Enhanced Signup Bot - Full Automation with SMS & CAPTCHA Handling

This is an advanced version of the signup bot that integrates:
- SMS verification via SMS-Activate/5sim
- CAPTCHA solving via CapSolver/2Captcha
- Agent callbacks for human-in-the-loop

Usage:
    python signup_bot_enhanced.py

Requires:
    - SBR_CDP_URL (Bright Data Scraping Browser)
    - OPENAI_API_KEY
    - SMS_ACTIVATE_API_KEY or FIVESIM_API_KEY
    - CAPSOLVER_API_KEY or TWO_CAPTCHA_API_KEY
"""

from browser_use import Agent, Browser, BrowserConfig
from browser_use.agent.views import AgentHistoryList
from langchain_openai import ChatOpenAI
import asyncio
import os
import json
import random
import string
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from faker import Faker
from typing import Optional, Callable, Any
import logging

# Local imports
from sms_service import SMSService, PhoneNumber
from captcha_solver import CaptchaSolver, CaptchaSolution

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Faker
fake = Faker('en_US')


class PersonaGenerator:
    """Generate realistic user personas."""
    
    @staticmethod
    def generate() -> dict:
        first_name = fake.first_name()
        last_name = fake.last_name()
        
        username_styles = [
            f"{first_name.lower()}{last_name.lower()}{random.randint(1, 999)}",
            f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 99)}",
            f"{first_name.lower()}_{random.randint(100, 9999)}",
        ]
        username = random.choice(username_styles)
        
        password = PersonaGenerator._generate_password()
        
        days_ago = random.randint(18 * 365, 40 * 365)
        birthdate = datetime.now() - timedelta(days=days_ago)
        
        return {
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "password": password,
            "birthdate": {
                "month": birthdate.strftime("%B"),
                "day": birthdate.day,
                "year": birthdate.year
            },
            "gender": random.choice(["Male", "Female", "Rather not say"]),
        }
    
    @staticmethod
    def _generate_password(length: int = 16) -> str:
        password = [
            random.choice(string.ascii_uppercase),
            random.choice(string.ascii_lowercase),
            random.choice(string.digits),
            random.choice("!@#$%^&*()_+-="),
        ]
        all_chars = string.ascii_letters + string.digits + "!@#$%^&*()_+-="
        password.extend(random.choices(all_chars, k=length - 4))
        random.shuffle(password)
        return ''.join(password)


class SignupBot:
    """
    Enhanced signup bot with full automation capabilities.
    
    Features:
        - Stealth browser via CDP
        - Human-like behavior prompts
        - SMS verification handling
        - CAPTCHA solving
        - Session persistence
        - Interactive callbacks
    """
    
    def __init__(
        self,
        target_url: str,
        cdp_url: Optional[str] = None,
        model: str = "gpt-4o",
        max_steps: int = 50,
        interactive: bool = True,
    ):
        self.target_url = target_url
        self.cdp_url = cdp_url or os.getenv("SBR_CDP_URL")
        self.model = model
        self.max_steps = max_steps
        self.interactive = interactive
        
        # State
        self.browser: Optional[Browser] = None
        self.agent: Optional[Agent] = None
        self.persona: Optional[dict] = None
        self.phone: Optional[PhoneNumber] = None
        self.sms: Optional[SMSService] = None
        self.captcha: Optional[CaptchaSolver] = None
        
        # Directories
        self.session_dir = Path(os.getenv("SESSION_DIR", "./sessions"))
        self.screenshot_dir = Path(os.getenv("SCREENSHOT_DIR", "./screenshots"))
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    async def __aenter__(self):
        """Initialize services."""
        # Initialize SMS service
        try:
            self.sms = SMSService()
            await self.sms.__aenter__()
            logger.info("SMS service initialized")
        except ValueError as e:
            logger.warning(f"SMS service not available: {e}")
        
        # Initialize CAPTCHA solver
        try:
            self.captcha = CaptchaSolver()
            await self.captcha.__aenter__()
            logger.info("CAPTCHA solver initialized")
        except ValueError as e:
            logger.warning(f"CAPTCHA solver not available: {e}")
        
        return self
    
    async def __aexit__(self, *args):
        """Cleanup services."""
        if self.sms:
            await self.sms.__aexit__(*args)
        if self.captcha:
            await self.captcha.__aexit__(*args)
        if self.browser:
            await self.browser.close()
    
    def build_task_prompt(self, persona: dict) -> str:
        """Build the agent task prompt with human-like behavior instructions."""
        return f"""
# OBJECTIVE
Create a new email account on {self.target_url}

# GENERATED PERSONA
- First Name: {persona['first_name']}
- Last Name: {persona['last_name']}
- Username: {persona['username']}
- Password: {persona['password']}
- Birth Month: {persona['birthdate']['month']}
- Birth Day: {persona['birthdate']['day']}
- Birth Year: {persona['birthdate']['year']}
- Gender: {persona['gender']}

# HUMAN-LIKE BEHAVIOR (CRITICAL FOR EVASION)
Act like a real human user:

1. **Mouse Movement**
   - Move in natural arcs, not straight lines
   - Pause 200-500ms before clicking (hesitation)
   - Occasionally overshoot slightly and correct

2. **Typing**
   - Variable speed (don't type at constant rate)
   - Pause between fields as if reading
   
3. **Timing**
   - Wait 1-3 seconds between major actions
   - Don't rush through the form

# STEP-BY-STEP WORKFLOW

## Step 1: Navigate
- Go to {self.target_url}
- Wait for page to fully load
- Move mouse casually (looking around)

## Step 2: Fill Registration Form
a. First Name: "{persona['first_name']}"
b. Last Name: "{persona['last_name']}"
c. Username: "{persona['username']}"
   - If taken, try appending random numbers
d. Password: "{persona['password']}"
e. Confirm Password: "{persona['password']}"
f. Month: "{persona['birthdate']['month']}"
g. Day: "{persona['birthdate']['day']}"
h. Year: "{persona['birthdate']['year']}"
i. Gender: "{persona['gender']}" (if required)

## Step 3: Handle Verification

### If CAPTCHA appears:
- Say: "CAPTCHA_DETECTED: [type: reCAPTCHA/hCaptcha/other] [site_key if visible]"
- Wait for my response with the solution token

### If Phone Verification required:
- Say: "PHONE_REQUIRED"
- Wait for my response with the phone number
- After entering number, if SMS code needed:
- Say: "SMS_CODE_REQUIRED"
- Wait for my response with the code

## Step 4: Complete Registration
- Click Submit/Create/Sign Up
- Handle any additional steps
- Continue until you reach inbox/welcome

## Step 5: Confirm Success
- Verify you are logged in
- Report: "SUCCESS: Account created for {persona['username']}"

# ERROR HANDLING
- If username taken: try modified username
- If blocked: report "BLOCKED: Bot detection triggered"
- If stuck: ask for help

# IMPORTANT
- NEVER rush
- Act human
- Ask for help if stuck
"""
    
    async def handle_agent_message(self, message: str) -> str:
        """
        Handle messages from the agent that require intervention.
        
        This callback processes requests for phone numbers, SMS codes,
        and CAPTCHA solutions.
        """
        message_upper = message.upper()
        
        # Handle CAPTCHA detection
        if "CAPTCHA_DETECTED" in message_upper:
            if not self.captcha:
                if self.interactive:
                    return input("CAPTCHA detected. Please solve it manually and press Enter: ")
                else:
                    return "Please solve the CAPTCHA manually."
            
            # Extract CAPTCHA type and site key if provided
            captcha_type = "recaptcha_v2"  # Default
            site_key = None
            
            if "HCAPTCHA" in message_upper:
                captcha_type = "hcaptcha"
            elif "RECAPTCHA" in message_upper or "RECAPTCHA" in message_upper:
                if "V3" in message_upper:
                    captcha_type = "recaptcha_v3"
                else:
                    captcha_type = "recaptcha_v2"
            
            # Try to extract site key from message
            import re
            key_match = re.search(r'site_key[:\s]*([a-zA-Z0-9_-]{40})', message, re.IGNORECASE)
            if key_match:
                site_key = key_match.group(1)
            
            if not site_key:
                if self.interactive:
                    site_key = input("Enter the CAPTCHA site key: ")
                else:
                    return "Could not determine CAPTCHA site key."
            
            try:
                if captcha_type == "hcaptcha":
                    solution = await self.captcha.solve_hcaptcha(site_key, self.target_url)
                elif captcha_type == "recaptcha_v3":
                    solution = await self.captcha.solve_recaptcha_v3(site_key, self.target_url)
                else:
                    solution = await self.captcha.solve_recaptcha_v2(site_key, self.target_url)
                
                logger.info(f"CAPTCHA solved: {solution.token[:30]}...")
                return f"CAPTCHA_TOKEN: {solution.token}"
            except Exception as e:
                logger.error(f"CAPTCHA solving failed: {e}")
                return f"CAPTCHA solving failed: {e}. Please solve manually."
        
        # Handle phone verification request
        if "PHONE_REQUIRED" in message_upper:
            if not self.sms:
                if self.interactive:
                    return input("Enter phone number (with country code): ")
                else:
                    return "SMS service not configured."
            
            try:
                # Get a phone number
                self.phone = await self.sms.get_number(service="google", country="russia")
                logger.info(f"Got phone number: +{self.phone.number}")
                return f"PHONE_NUMBER: +{self.phone.number}"
            except Exception as e:
                logger.error(f"Failed to get phone number: {e}")
                if self.interactive:
                    return input("Failed to get virtual number. Enter phone manually: ")
                else:
                    return f"Failed to get phone number: {e}"
        
        # Handle SMS code request
        if "SMS_CODE_REQUIRED" in message_upper:
            if not self.sms or not self.phone:
                if self.interactive:
                    return input("Enter SMS verification code: ")
                else:
                    return "SMS service not configured."
            
            try:
                logger.info("Waiting for SMS code...")
                code = await self.sms.wait_for_code(timeout=120)
                logger.info(f"Received SMS code: {code}")
                return f"SMS_CODE: {code}"
            except TimeoutError:
                logger.error("SMS code not received within timeout")
                if self.interactive:
                    return input("SMS code not received. Enter manually: ")
                else:
                    return "SMS code not received within timeout."
            except Exception as e:
                logger.error(f"Failed to get SMS code: {e}")
                if self.interactive:
                    return input(f"Error: {e}. Enter SMS code manually: ")
                else:
                    return f"Failed to get SMS code: {e}"
        
        # Default: pass through to user if interactive
        if self.interactive:
            return input(f"Agent says: {message}\nYour response: ")
        else:
            return "Unable to process request automatically."
    
    async def run(self, persona: Optional[dict] = None) -> dict:
        """
        Run the signup bot.
        
        Args:
            persona: Optional persona dict. If not provided, one will be generated.
        
        Returns:
            Dict with result status, persona, and session info.
        """
        # Generate or use provided persona
        self.persona = persona or PersonaGenerator.generate()
        
        logger.info("=" * 60)
        logger.info("Enhanced Signup Bot - Starting")
        logger.info("=" * 60)
        logger.info(f"Target: {self.target_url}")
        logger.info(f"Persona: {self.persona['first_name']} {self.persona['last_name']}")
        logger.info(f"Username: {self.persona['username']}")
        
        # Validate configuration
        if not self.cdp_url:
            raise ValueError("SBR_CDP_URL not configured")
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY not configured")
        
        # Initialize browser
        logger.info("Connecting to stealth browser...")
        self.browser = Browser(
            config=BrowserConfig(
                cdp_url=self.cdp_url,
                disable_security=True,
            )
        )
        
        # Initialize LLM
        llm = ChatOpenAI(
            model=self.model,
            temperature=0.7,
        )
        
        # Build task prompt
        task = self.build_task_prompt(self.persona)
        
        # Create agent
        self.agent = Agent(
            task=task,
            llm=llm,
            browser=self.browser,
        )
        
        result = {
            "success": False,
            "persona": self.persona,
            "session_file": None,
            "screenshot": None,
            "error": None,
        }
        
        try:
            logger.info("Starting agent execution...")
            
            # Run agent with message callback
            # Note: browser-use may not support callbacks directly
            # This is a simplified version - real implementation would need
            # to hook into the agent's message handling
            history = await self.agent.run(max_steps=self.max_steps)
            
            if history.is_done():
                logger.info("SUCCESS: Agent completed task!")
                result["success"] = True
                
                # Take screenshot
                try:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    screenshot_path = self.screenshot_dir / f"success_{self.persona['username']}_{timestamp}.png"
                    page = self.browser.playwright_browser.contexts[0].pages[0]
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    result["screenshot"] = str(screenshot_path)
                    logger.info(f"Screenshot saved: {screenshot_path}")
                except Exception as e:
                    logger.warning(f"Failed to take screenshot: {e}")
                
                # Save session
                try:
                    session_path = self.session_dir / f"{self.persona['username']}_session.json"
                    context = self.browser.playwright_browser.contexts[0]
                    await context.storage_state(path=str(session_path))
                    result["session_file"] = str(session_path)
                    logger.info(f"Session saved: {session_path}")
                    
                    # Save persona
                    persona_path = self.session_dir / f"{self.persona['username']}_persona.json"
                    with open(persona_path, 'w') as f:
                        json.dump(self.persona, f, indent=2)
                except Exception as e:
                    logger.warning(f"Failed to save session: {e}")
            else:
                logger.warning("Agent did not complete task")
                result["error"] = "Task not completed"
                
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            result["error"] = str(e)
            
            # Take error screenshot
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = self.screenshot_dir / f"error_{self.persona['username']}_{timestamp}.png"
                page = self.browser.playwright_browser.contexts[0].pages[0]
                await page.screenshot(path=str(screenshot_path), full_page=True)
                result["screenshot"] = str(screenshot_path)
            except:
                pass
        
        finally:
            if self.browser:
                await self.browser.close()
        
        # Log summary
        logger.info("=" * 60)
        logger.info("Execution Summary")
        logger.info("=" * 60)
        logger.info(f"Status: {'SUCCESS' if result['success'] else 'FAILED'}")
        logger.info(f"Username: {self.persona['username']}")
        logger.info(f"Password: {self.persona['password']}")
        if result['error']:
            logger.info(f"Error: {result['error']}")
        
        return result


async def main():
    """Main entry point."""
    
    # Configuration
    TARGET_URL = "https://accounts.google.com/signup"  # Replace with actual target
    
    async with SignupBot(
        target_url=TARGET_URL,
        interactive=True,  # Enable user prompts
        max_steps=50,
    ) as bot:
        result = await bot.run()
        
        if result["success"]:
            print("\n✅ Account created successfully!")
            print(f"   Username: {result['persona']['username']}")
            print(f"   Password: {result['persona']['password']}")
            print(f"   Session: {result['session_file']}")
        else:
            print(f"\n❌ Account creation failed: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
