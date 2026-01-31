"""
AtomicMail Signup Bot with Manual CAPTCHA and Database Integration

This bot automates account creation on AtomicMail with:
- Multi-step form filling
- Manual CAPTCHA solving (pauses for user)
- Seed phrase capture
- SQLite database storage

Usage:
    python atomicmail_bot.py

Requirements:
    - Chrome/Chromium browser
    - playwright (pip install playwright && playwright install chromium)
"""

import asyncio
import os
import sys
import random
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import logging
import json

from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from faker import Faker
from dotenv import load_dotenv

# Local imports
from database import get_database, Database

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("atomicmail_bot.log")
    ]
)
logger = logging.getLogger(__name__)

# Initialize Faker
fake = Faker('en_US')


class PersonaGenerator:
    """Generate realistic user personas for AtomicMail."""
    
    @staticmethod
    def generate() -> dict:
        first_name = fake.first_name()
        last_name = fake.last_name()
        
        # AtomicMail only allows letters, numbers, and periods (NO underscores)
        username_styles = [
            f"{first_name.lower()}{last_name.lower()}{random.randint(1, 999)}",
            f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 99)}",
            f"{first_name.lower()}{random.randint(100, 9999)}",
        ]
        username = random.choice(username_styles)
        
        # Generate strong password
        password = PersonaGenerator._generate_password()
        
        # Generate birthdate (18-40 years old)
        days_ago = random.randint(18 * 365, 40 * 365)
        birthdate = datetime.now() - timedelta(days=days_ago)
        
        return {
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "email": f"{username}@atomicmail.io",
            "password": password,
            "birthdate": {
                "month": birthdate.strftime("%B"),
                "day": birthdate.day,
                "year": birthdate.year
            },
            "gender": random.choice(["Male", "Female"]),
        }
    
    @staticmethod
    def _generate_password(length: int = 16) -> str:
        """Generate password with letters, numbers, and symbols (AtomicMail requirement)."""
        password = [
            random.choice(string.ascii_uppercase),
            random.choice(string.ascii_lowercase),
            random.choice(string.digits),
            random.choice("!@#$%^&*"),
        ]
        all_chars = string.ascii_letters + string.digits + "!@#$%^&*"
        password.extend(random.choices(all_chars, k=length - 4))
        random.shuffle(password)
        return ''.join(password)


class AtomicMailBot:
    """
    AtomicMail account creation bot with manual CAPTCHA solving.
    
    Features:
        - Automated multi-step form filling
        - Pauses for manual CAPTCHA solving
        - Captures seed phrase using copy button
        - Saves all data to SQLite database
    """
    
    SIGNUP_URL = "https://atomicmail.io/app/auth/sign-up"
    
    def __init__(
        self,
        headless: bool = False,
        slow_mo: int = 100,
    ):
        self.headless = headless
        self.slow_mo = slow_mo
        
        # State
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.persona: Optional[dict] = None
        self.seed_phrase: Optional[str] = None
        self.db: Database = get_database()
        
        # Directories
        self.screenshot_dir = Path("./screenshots")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    async def start_browser(self):
        """Start the Playwright browser."""
        playwright = await async_playwright().start()
        
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )
        
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        self.page = await self.context.new_page()
        logger.info("Browser started")
    
    async def close_browser(self):
        """Close the browser."""
        if self.browser:
            await self.browser.close()
            logger.info("Browser closed")
    
    async def human_delay(self, min_ms: int = 500, max_ms: int = 1500):
        """Random delay to mimic human behavior."""
        delay = random.randint(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)
    
    async def human_type(self, selector: str, text: str):
        """Type text with human-like delays."""
        await self.page.click(selector)
        await self.human_delay(200, 400)
        
        # Type with variable speed
        for char in text:
            await self.page.keyboard.type(char, delay=random.randint(50, 150))
    
    async def take_screenshot(self, name: str) -> str:
        """Take a screenshot and return the path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.screenshot_dir / f"{name}_{timestamp}.png"
        await self.page.screenshot(path=str(path), full_page=True)
        logger.info(f"Screenshot saved: {path}")
        return str(path)
    
    async def step_1_names(self):
        """Step 1: Fill first and last name."""
        logger.info("Step 1: Filling names...")
        
        # Wait for form to load - look for the text labels instead
        await self.page.wait_for_selector('text=First name', timeout=15000)
        await self.human_delay()
        
        # Fill first name - use label-based selector
        first_name_input = await self.page.query_selector('input[placeholder*="Alfred"], input[placeholder*="first"], input:near(:text("First name"))')
        if first_name_input:
            await first_name_input.click()
            await self.human_delay(200, 400)
            await first_name_input.type(self.persona['first_name'], delay=random.randint(50, 150))
        else:
            # Fallback: click the input below "First name" label
            await self.page.click('text=First name')
            await self.page.keyboard.press('Tab')
            await self.page.keyboard.type(self.persona['first_name'])
        await self.human_delay()
        
        # Fill last name (optional but we fill it)
        last_name_input = await self.page.query_selector('input[placeholder*="Hitchcock"], input[placeholder*="last"], input:near(:text("Last name"))')
        if last_name_input:
            await last_name_input.click()
            await self.human_delay(200, 400)
            await last_name_input.type(self.persona['last_name'], delay=random.randint(50, 150))
        else:
            await self.page.click('text=Last name')
            await self.page.keyboard.press('Tab')
            await self.page.keyboard.type(self.persona['last_name'])
        await self.human_delay()
        
        # Click submit
        await self.page.click('button:has-text("Submit")')
        await self.human_delay(1000, 2000)
        
        logger.info(f"  Entered: {self.persona['first_name']} {self.persona['last_name']}")
    
    async def step_2_email(self):
        """Step 2: Fill email address."""
        logger.info("Step 2: Filling email address...")
        
        # Wait for email step - the page title indicates we're on the right step
        await self.page.wait_for_selector('text=Your mail address', timeout=15000)
        await self.human_delay()
        
        # Fill username (without @atomicmail.io - it's added automatically)
        username = self.persona['username']
        email_input = await self.page.query_selector('input[placeholder*=\"alfie\"], input[placeholder*=\"hitchcock\"]')
        if email_input:
            await email_input.click()
            await self.human_delay(200, 400)
            await email_input.type(username, delay=random.randint(50, 150))
        else:
            # Fallback - get the only visible input
            await self.page.fill('input:visible', username)
        await self.human_delay()
        
        # Click submit
        await self.page.click('button:has-text("Submit")')
        await self.human_delay(1000, 2000)
        
        # Check for error (username taken or invalid)
        error = await self.page.query_selector('.error-message, .text-red-500, [class*="error"]')
        if error:
            error_text = await error.text_content()
            logger.warning(f"  Error: {error_text}")
            
            # Try with modified username
            new_username = f"{username}{random.randint(100, 999)}"
            logger.info(f"  Retrying with: {new_username}")
            
            await self.page.fill('input[placeholder="Your mail address"]', "")
            await self.human_type('input[placeholder="Your mail address"]', new_username)
            await self.human_delay()
            await self.page.click('button:has-text("Submit")')
            await self.human_delay(1000, 2000)
            
            self.persona['username'] = new_username
            self.persona['email'] = f"{new_username}@atomicmail.io"
        
        logger.info(f"  Email: {self.persona['email']}")
    
    async def step_3_password(self):
        """Step 3: Fill password and confirm."""
        logger.info("Step 3: Filling password...")
        
        # Wait for password step - look for the title
        await self.page.wait_for_selector('text=Create a strong password', timeout=15000)
        await self.human_delay()
        
        # Fill password - placeholder is "e.g. 1Ush3tajK"
        password_input = await self.page.query_selector('input[placeholder*="1Ush3tajK"], input[type="password"]:first-of-type')
        if password_input:
            await password_input.click()
            await self.human_delay(200, 400)
            await password_input.type(self.persona['password'], delay=random.randint(50, 150))
        else:
            # Fallback - get first password input
            inputs = await self.page.query_selector_all('input[type="password"]')
            if inputs:
                await inputs[0].click()
                await self.human_delay(200, 400)
                await inputs[0].type(self.persona['password'], delay=random.randint(50, 150))
        await self.human_delay()
        
        # Fill confirm password - should be second password input
        confirm_input = await self.page.query_selector_all('input[type="password"]')
        if len(confirm_input) >= 2:
            await confirm_input[1].click()
            await self.human_delay(200, 400)
            await confirm_input[1].type(self.persona['password'], delay=random.randint(50, 150))
        elif len(confirm_input) == 1:
            # Only one password field visible, maybe need to look for explicit confirm
            confirm_field = await self.page.query_selector('input[placeholder*="Confirm"], input:near(:text("Confirm"))')
            if confirm_field:
                await confirm_field.click()
                await self.human_delay(200, 400)
                await confirm_field.type(self.persona['password'], delay=random.randint(50, 150))
        await self.human_delay()
        
        # Click submit
        await self.page.click('button:has-text("Submit")')
        await self.human_delay(1000, 2000)
        
        logger.info("  Password set")
    
    async def step_4_seed_phrase(self):
        """Step 4: Copy and save seed phrase."""
        logger.info("Step 4: Capturing seed phrase...")
        
        # Wait for seed phrase section
        await self.page.wait_for_selector('text=Save your Seed Phrase', timeout=10000)
        await self.human_delay()
        
        # Take screenshot of seed phrase
        await self.take_screenshot("seed_phrase")
        
        # Try to copy seed phrase using the copy button
        try:
            # Look for checkbox or copy button
            copy_button = await self.page.query_selector('text=Copy seed phrase')
            if copy_button:
                await copy_button.click()
                await self.human_delay(500, 1000)
                
                # Get from clipboard
                self.seed_phrase = await self.page.evaluate("""
                    async () => {
                        try {
                            return await navigator.clipboard.readText();
                        } catch (e) {
                            return null;
                        }
                    }
                """)
            
            # If clipboard didn't work, try to extract from DOM
            if not self.seed_phrase:
                # Look for the seed phrase words in the grid
                seed_words = await self.page.evaluate("""
                    () => {
                        // Try to find the seed phrase grid
                        const words = document.querySelectorAll('[class*="seed"] span, [class*="phrase"] span, .grid span');
                        if (words.length >= 12) {
                            return Array.from(words).slice(0, 12).map(w => w.textContent.trim()).join(' ');
                        }
                        
                        // Alternative: look for specific word buttons
                        const buttons = document.querySelectorAll('button span, div[class*="word"]');
                        const seedWords = [];
                        for (const btn of buttons) {
                            const text = btn.textContent.trim().toLowerCase();
                            // Filter to likely seed words (short, lowercase, no numbers)
                            if (text.length >= 3 && text.length <= 10 && /^[a-z]+$/.test(text)) {
                                seedWords.push(text);
                            }
                        }
                        return seedWords.slice(0, 12).join(' ');
                    }
                """)
                self.seed_phrase = seed_words if seed_words else "MANUAL_EXTRACTION_REQUIRED"
        
        except Exception as e:
            logger.warning(f"  Could not auto-extract seed phrase: {e}")
            self.seed_phrase = "MANUAL_EXTRACTION_REQUIRED"
        
        if self.seed_phrase and self.seed_phrase != "MANUAL_EXTRACTION_REQUIRED":
            logger.info(f"  Seed phrase captured: {self.seed_phrase[:30]}...")
        else:
            # Ask user to manually copy if auto-extraction failed
            print("\n" + "=" * 60)
            print("SEED PHRASE EXTRACTION")
            print("=" * 60)
            print("Could not auto-extract seed phrase.")
            print("Please manually copy the seed phrase from the browser.")
            print("Then paste it here:")
            self.seed_phrase = input("> ").strip()
        
        logger.info("  Seed phrase captured and ready to save")
    
    async def step_5_complete_signup(self) -> bool:
        """Step 5: Click Download & Proceed and handle CAPTCHA."""
        logger.info("Step 5: Completing signup...")
        
        # Click Download & Proceed
        proceed_button = await self.page.query_selector('button:has-text("Download & Proceed")')
        if proceed_button:
            await proceed_button.click()
            await self.human_delay(2000, 3000)
        
        # Check for CAPTCHA
        captcha_detected = await self.page.query_selector('iframe[src*="captcha"], iframe[src*="hcaptcha"], iframe[src*="recaptcha"]')
        
        if captcha_detected:
            logger.info("  CAPTCHA detected! Pausing for manual solving...")
            await self.take_screenshot("captcha_detected")
            
            # MANUAL CAPTCHA HANDLING
            print("\n" + "=" * 60)
            print("🔐 CAPTCHA DETECTED - MANUAL INTERVENTION REQUIRED")
            print("=" * 60)
            print(f"Browser window: {self.page.url}")
            print("\nPlease solve the CAPTCHA in the browser window.")
            print("The bot will wait for you to complete it.")
            print("\nPress ENTER when you have solved the CAPTCHA...")
            input()
            
            await self.human_delay(1000, 2000)
            await self.take_screenshot("captcha_solved")
            logger.info("  User indicated CAPTCHA solved, continuing...")
        
        # Wait for page to change (success or another step)
        await self.human_delay(2000, 3000)
        
        # Check for success indicators
        current_url = self.page.url
        success_indicators = [
            "/app/mail",
            "/inbox",
            "/dashboard",
            "welcome",
        ]
        
        is_success = any(indicator in current_url.lower() for indicator in success_indicators)
        
        if not is_success:
            # Check for success text
            page_content = await self.page.content()
            if "account created" in page_content.lower() or "welcome" in page_content.lower():
                is_success = True
        
        if is_success:
            logger.info("  ✅ Signup successful!")
            await self.take_screenshot("signup_success")
            return True
        else:
            logger.warning("  ⚠️ Signup status unclear, check browser")
            await self.take_screenshot("signup_unclear")
            
            print("\nDid the signup complete successfully? (y/n): ", end="")
            response = input().strip().lower()
            return response == 'y'
    
    async def save_to_database(self, success: bool) -> int:
        """Save account data to the database."""
        logger.info("Saving to database...")
        
        status = "active" if success else "failed"
        
        account_id = self.db.save_account(
            email=self.persona['email'],
            password=self.persona['password'],
            first_name=self.persona['first_name'],
            last_name=self.persona['last_name'],
            birth_month=self.persona['birthdate']['month'],
            birth_day=self.persona['birthdate']['day'],
            birth_year=self.persona['birthdate']['year'],
            gender=self.persona['gender'],
            seed_phrase=self.seed_phrase or "",
            platform="atomicmail",
            status=status,
            notes=f"Created at {datetime.now().isoformat()}"
        )
        
        logger.info(f"  Saved to database with ID: {account_id}")
        return account_id
    
    async def run(self, persona: Optional[dict] = None) -> dict:
        """
        Run the complete signup flow.
        
        Args:
            persona: Optional persona dict. If not provided, one will be generated.
        
        Returns:
            Dict with result including success status, account ID, and credentials.
        """
        result = {
            "success": False,
            "account_id": None,
            "persona": None,
            "seed_phrase": None,
            "error": None,
        }
        
        try:
            # Generate persona
            self.persona = persona or PersonaGenerator.generate()
            result["persona"] = self.persona
            
            # Print persona info
            print("\n" + "=" * 60)
            print("🚀 ATOMICMAIL SIGNUP BOT")
            print("=" * 60)
            print(f"Name: {self.persona['first_name']} {self.persona['last_name']}")
            print(f"Email: {self.persona['email']}")
            print(f"Password: {self.persona['password']}")
            print("=" * 60 + "\n")
            
            # Start browser
            await self.start_browser()
            
            # Navigate to signup
            logger.info(f"Navigating to {self.SIGNUP_URL}")
            await self.page.goto(self.SIGNUP_URL, wait_until="domcontentloaded", timeout=60000)
            await self.human_delay(2000, 3000)
            
            # Execute steps
            await self.step_1_names()
            await self.step_2_email()
            await self.step_3_password()
            await self.step_4_seed_phrase()
            success = await self.step_5_complete_signup()
            
            result["success"] = success
            result["seed_phrase"] = self.seed_phrase
            
            # Save to database
            account_id = await self.save_to_database(success)
            result["account_id"] = account_id
            
        except Exception as e:
            logger.error(f"Signup failed: {e}")
            result["error"] = str(e)
            await self.take_screenshot("error")
        
        finally:
            # Keep browser open for inspection if there was an error
            if not result["success"] and result["error"]:
                print("\nBrowser kept open for inspection. Press ENTER to close...")
                input()
            
            await self.close_browser()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 SIGNUP SUMMARY")
        print("=" * 60)
        if result["success"]:
            print("✅ Status: SUCCESS")
            print(f"📧 Email: {result['persona']['email']}")
            print(f"🔑 Password: {result['persona']['password']}")
            print(f"🌱 Seed Phrase: {result['seed_phrase'][:40]}..." if result['seed_phrase'] else "N/A")
            print(f"💾 Database ID: {result['account_id']}")
        else:
            print("❌ Status: FAILED")
            print(f"Error: {result['error']}")
        print("=" * 60 + "\n")
        
        return result


async def main():
    """Main entry point."""
    
    # Ensure database is initialized
    db = get_database()
    print(f"Database: {db.db_path}")
    
    # Run bot
    bot = AtomicMailBot(
        headless=False,  # Show browser for CAPTCHA solving
        slow_mo=50,      # Slight slowdown for human-like behavior
    )
    
    result = await bot.run()
    
    # Show database stats
    stats = db.get_stats()
    print(f"\n📈 Database Stats: {stats['total_accounts']} total accounts")
    
    return result


if __name__ == "__main__":
    asyncio.run(main())
