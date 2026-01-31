"""
Signup Bot - Automated Account Creation with browser-use

This bot uses browser-use with a stealth CDP connection to create accounts
on high-security email platforms while evading bot detection.

Architecture:
    - Stealth Browser: Bright Data Scraping Browser (residential proxies, TLS spoofing)
    - Orchestration: browser-use Agent
    - LLM: GPT-4o via langchain-openai
    - Session Persistence: Playwright storage_state

Usage:
    1. Copy .env.example to .env and fill in your API keys
    2. Run: python signup_bot.py
"""

from browser_use import Agent, Browser, BrowserConfig
from browser_use.browser.context import BrowserContext
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
from typing import Optional
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Faker for persona generation
fake = Faker('en_US')


class PersonaGenerator:
    """Generate realistic user personas for account creation."""
    
    @staticmethod
    def generate() -> dict:
        """Generate a complete user persona."""
        first_name = fake.first_name()
        last_name = fake.last_name()
        
        # Generate username variations
        username_styles = [
            f"{first_name.lower()}{last_name.lower()}{random.randint(1, 999)}",
            f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 99)}",
            f"{first_name.lower()}_{random.randint(100, 9999)}",
            f"{last_name.lower()}{first_name[0].lower()}{random.randint(10, 999)}",
        ]
        username = random.choice(username_styles)
        
        # Generate strong password (16+ chars, mixed case, numbers, symbols)
        password = PersonaGenerator._generate_password()
        
        # Generate birthdate (18-45 years old)
        min_age = 18
        max_age = 45
        days_ago = random.randint(min_age * 365, max_age * 365)
        birthdate = datetime.now() - timedelta(days=days_ago)
        
        return {
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "password": password,
            "birthdate": {
                "month": birthdate.strftime("%B"),  # Full month name
                "day": birthdate.day,
                "year": birthdate.year
            },
            "gender": random.choice(["Male", "Female", "Rather not say"]),
        }
    
    @staticmethod
    def _generate_password(length: int = 16) -> str:
        """Generate a secure password meeting complexity requirements."""
        # Ensure at least one of each required type
        password = [
            random.choice(string.ascii_uppercase),
            random.choice(string.ascii_lowercase),
            random.choice(string.digits),
            random.choice("!@#$%^&*()_+-=[]{}|;:,.<>?"),
        ]
        
        # Fill remaining length with random chars
        all_chars = string.ascii_letters + string.digits + "!@#$%^&*()_+-="
        password.extend(random.choices(all_chars, k=length - 4))
        
        # Shuffle to avoid predictable pattern
        random.shuffle(password)
        return ''.join(password)


def build_signup_task(persona: dict, target_url: str) -> str:
    """
    Build a detailed task prompt for the Agent.
    
    The prompt includes human-like behavior instructions to evade detection.
    """
    return f"""
# OBJECTIVE
Create a new email account on {target_url}

# PERSONA DETAILS
- First Name: {persona['first_name']}
- Last Name: {persona['last_name']}  
- Username: {persona['username']}
- Password: {persona['password']}
- Birth Month: {persona['birthdate']['month']}
- Birth Day: {persona['birthdate']['day']}
- Birth Year: {persona['birthdate']['year']}
- Gender: {persona['gender']}

# HUMAN-LIKE BEHAVIOR INSTRUCTIONS
You MUST behave like a real human to avoid bot detection:

1. **Mouse Movement**: Move the cursor in natural arcs (Bezier curves), not straight lines.
   - Hover over elements briefly before clicking (200-500ms hesitation).
   - Occasionally overshoot the target slightly and correct.

2. **Typing Patterns**: Type at a natural pace.
   - Vary typing speed (don't type at constant intervals).
   - Make occasional typos and correct them (optional, be careful).
   - Pause briefly between fields as if reading.

3. **Scrolling**: Scroll smoothly, not instantly.
   - Small scroll increments to "read" the page.

4. **Timing**: Add natural delays between actions.
   - Don't rush through the form.
   - Wait 1-3 seconds between major actions.

# STEP-BY-STEP WORKFLOW

1. **Navigate** to the signup page at {target_url}
   - Wait for the page to fully load.
   - Take a moment to "look around" (move mouse casually).

2. **Fill the Registration Form**
   a. Enter First Name: "{persona['first_name']}"
   b. Enter Last Name: "{persona['last_name']}"
   c. Enter Username/Email: "{persona['username']}"
      - If username is taken, try appending random numbers.
   d. Enter Password: "{persona['password']}"
   e. Confirm Password: "{persona['password']}"
   f. Select Birth Month: "{persona['birthdate']['month']}"
   g. Select Birth Day: "{persona['birthdate']['day']}"
   h. Select Birth Year: "{persona['birthdate']['year']}"
   i. Select Gender: "{persona['gender']}" (if required)

3. **Handle Verification Challenges**
   
   a. **CAPTCHA**: 
      - If you see a CAPTCHA (reCAPTCHA, hCaptcha, puzzle, etc.):
      - Try to solve it if it's simple (image selection).
      - If you cannot solve it, STOP and ask me: "CAPTCHA detected. Please solve manually."
   
   b. **Phone Verification**:
      - If the site requires a phone number:
      - STOP and ask me: "Phone verification required. Please provide a phone number."
      - Wait for my response with the phone number.
      - After entering the number, if an SMS code is needed:
      - STOP and ask me: "SMS code required. What is the verification code?"
   
   c. **Email Verification**:
      - If it requires verifying via another email, ask me for instructions.

4. **Complete Registration**
   - Click the "Create Account" / "Sign Up" / "Next" button.
   - Handle any additional steps (terms acceptance, optional features, etc.).
   - Continue until you reach the inbox/welcome screen.

5. **Confirm Success**
   - Verify you are logged in (inbox visible, welcome message, etc.).
   - Take a screenshot as proof.
   - Report: "SUCCESS: Account created for {persona['username']}"

# ERROR HANDLING
- If any step fails, report the specific error.
- If the account/username is already taken, try with a modified username.
- If blocked or detected as bot, report: "BLOCKED: Bot detection triggered."

# IMPORTANT
- NEVER rush. Act human.
- If stuck, ask for help rather than failing silently.
"""


async def save_session(browser: Browser, persona: dict, session_dir: str = "./sessions"):
    """
    Save browser session state for future logins.
    
    This prevents the account from being flagged as "new device" on next login.
    """
    Path(session_dir).mkdir(parents=True, exist_ok=True)
    
    session_file = Path(session_dir) / f"{persona['username']}_session.json"
    
    try:
        # Get the browser context's storage state
        context = browser.playwright_browser.contexts[0] if browser.playwright_browser.contexts else None
        if context:
            await context.storage_state(path=str(session_file))
            logger.info(f"Session saved to {session_file}")
            
            # Also save persona details for reference
            persona_file = Path(session_dir) / f"{persona['username']}_persona.json"
            with open(persona_file, 'w') as f:
                json.dump(persona, f, indent=2)
            logger.info(f"Persona saved to {persona_file}")
            
            return str(session_file)
    except Exception as e:
        logger.error(f"Failed to save session: {e}")
        return None


async def take_screenshot(browser: Browser, name: str, screenshot_dir: str = "./screenshots"):
    """Take a screenshot for debugging/verification."""
    Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_file = Path(screenshot_dir) / f"{name}_{timestamp}.png"
    
    try:
        page = browser.playwright_browser.contexts[0].pages[0] if browser.playwright_browser.contexts else None
        if page:
            await page.screenshot(path=str(screenshot_file), full_page=True)
            logger.info(f"Screenshot saved to {screenshot_file}")
            return str(screenshot_file)
    except Exception as e:
        logger.error(f"Failed to take screenshot: {e}")
        return None


async def main():
    """Main entry point for the signup bot."""
    
    # ==========================================================================
    # Configuration
    # ==========================================================================
    
    # Target signup URL (replace with actual target)
    TARGET_URL = "https://accounts.google.com/signup"  # Example - replace as needed
    
    # Get CDP URL from environment
    cdp_url = os.getenv("SBR_CDP_URL")
    if not cdp_url:
        logger.error("SBR_CDP_URL not set. Please configure your .env file.")
        logger.info("See .env.example for configuration instructions.")
        return
    
    # Verify OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not set. Please configure your .env file.")
        return
    
    # ==========================================================================
    # Initialize Components
    # ==========================================================================
    
    logger.info("=" * 60)
    logger.info("Signup Bot - Starting")
    logger.info("=" * 60)
    
    # 1. Generate persona
    persona = PersonaGenerator.generate()
    logger.info(f"Generated persona: {persona['first_name']} {persona['last_name']}")
    logger.info(f"Username: {persona['username']}")
    
    # 2. Configure stealth browser via CDP
    # This connects to Bright Data Scraping Browser which handles:
    # - TLS fingerprinting
    # - Residential proxy rotation
    # - Browser fingerprint randomization
    # - CAPTCHA bypass (some types)
    logger.info("Connecting to stealth browser via CDP...")
    
    browser = Browser(
        config=BrowserConfig(
            cdp_url=cdp_url,
            disable_security=True,  # Required for cross-origin operations
            headless=False,  # Stealth browsers typically run headed in cloud
        )
    )
    
    # 3. Initialize LLM
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.7,  # Slight randomness for human-like decisions
    )
    
    # 4. Build task prompt
    signup_task = build_signup_task(persona, TARGET_URL)
    
    # 5. Create Agent
    agent = Agent(
        task=signup_task,
        llm=llm,
        browser=browser,
        # Optional: Enable sensitive data handling
        # include_attributes=["id", "class", "name", "placeholder", "type", "value", "aria-label"],
    )
    
    # ==========================================================================
    # Execute
    # ==========================================================================
    
    try:
        logger.info("Starting agent execution...")
        logger.info(f"Target: {TARGET_URL}")
        
        # Run the agent
        history = await agent.run(max_steps=50)  # Limit steps to prevent infinite loops
        
        # Check result
        if history.is_done():
            logger.info("Agent completed task successfully!")
            
            # Take success screenshot
            await take_screenshot(browser, f"success_{persona['username']}")
            
            # Save session for future use
            session_path = await save_session(browser, persona)
            if session_path:
                logger.info(f"Session saved: {session_path}")
        else:
            logger.warning("Agent did not complete the task.")
            await take_screenshot(browser, f"incomplete_{persona['username']}")
            
        # Log final result
        logger.info("=" * 60)
        logger.info("Execution Summary")
        logger.info("=" * 60)
        logger.info(f"Username: {persona['username']}")
        logger.info(f"Password: {persona['password']}")
        logger.info(f"Steps taken: {len(history.history) if hasattr(history, 'history') else 'N/A'}")
        
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        await take_screenshot(browser, f"error_{persona['username']}")
        raise
    
    finally:
        # Always close browser
        logger.info("Closing browser...")
        await browser.close()
        logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
