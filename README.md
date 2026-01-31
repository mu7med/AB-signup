# Automated Identity Creation Bot

A sophisticated account creation bot using **browser-use** with stealth browser connections, human-like behavior simulation, and automated verification handling.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Signup Bot                                  │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐  │
│  │   LLM       │  │   Browser   │  │   Verification Services     │  │
│  │  (GPT-4o)   │  │  (Stealth)  │  │  ┌─────────┐ ┌───────────┐  │  │
│  │             │  │             │  │  │   SMS   │ │  CAPTCHA  │  │  │
│  │  langchain  │  │  CDP/Bright │  │  │ Activate│ │  Solver   │  │  │
│  │  -openai    │  │   Data      │  │  └─────────┘ └───────────┘  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Target Website │
                    │  (Gmail, etc.)  │
                    └─────────────────┘
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

Required keys:
- `SBR_CDP_URL` - Bright Data Scraping Browser CDP URL
- `OPENAI_API_KEY` - OpenAI API key for GPT-4o

Optional (for full automation):
- `SMS_ACTIVATE_API_KEY` - For phone verification
- `CAPSOLVER_API_KEY` - For CAPTCHA solving

### 3. Run

```bash
# Basic bot (interactive mode)
python signup_bot.py

# Enhanced bot (with SMS/CAPTCHA handling)
python signup_bot_enhanced.py
```

## Files

| File | Description |
|------|-------------|
| `signup_bot.py` | Basic signup bot with human-like behavior prompts |
| `signup_bot_enhanced.py` | Full-featured bot with SMS & CAPTCHA integration |
| `sms_service.py` | SMS verification (SMS-Activate, 5sim) |
| `captcha_solver.py` | CAPTCHA solving (CapSolver, 2Captcha) |
| `.env.example` | Environment variables template |
| `requirements.txt` | Python dependencies |

## Configuration

### Stealth Browser (Required)

The bot uses a remote CDP connection to a stealth browser provider. This handles:
- TLS fingerprinting
- Residential proxy rotation  
- Browser fingerprint randomization
- Some CAPTCHA bypass

**Bright Data Scraping Browser:**
```
SBR_CDP_URL=wss://brd-customer-<ID>-zone-<ZONE>:<PASS>@brd.superproxy.io:9222
```

**Alternative: Browserbase:**
```
BROWSERBASE_CDP_URL=wss://connect.browserbase.com?apiKey=<KEY>
```

### SMS Verification (Optional)

For phone verification, configure one of:

**SMS-Activate:** (Recommended)
```
SMS_ACTIVATE_API_KEY=your-key
```

**5sim:**
```
FIVESIM_API_KEY=your-key
```

### CAPTCHA Solving (Optional)

**CapSolver:** (Recommended)
```
CAPSOLVER_API_KEY=your-key
```

**2Captcha:**
```
TWO_CAPTCHA_API_KEY=your-key
```

## Features

### Human-Like Behavior

The agent is instructed to:
- Move mouse in natural Bezier curves
- Pause before clicking (200-500ms hesitation)
- Type at variable speeds
- Wait between actions
- Occasionally overshoot targets

### Session Persistence

After successful signup:
- Browser state saved to `sessions/<username>_session.json`
- Prevents "new device" flags on future logins
- Reusable cookies/localStorage

### Error Handling

- Username taken → Retry with modified username
- CAPTCHA → Auto-solve or ask user
- Phone verification → Get virtual number or ask user
- Bot detection → Report and screenshot

## Project Structure

```
AB/
├── .agent/
│   ├── skills/          # AI agent skills
│   ├── rules/           # Development rules
│   ├── workflows/       # Command workflows
│   └── hooks/           # Pre/post hooks
├── sessions/            # Saved browser sessions
├── screenshots/         # Debug screenshots
├── signup_bot.py        # Basic bot
├── signup_bot_enhanced.py  # Full automation
├── sms_service.py       # SMS handling
├── captcha_solver.py    # CAPTCHA solving
├── requirements.txt     # Dependencies
└── .env                 # Configuration
```

## Skills Reference

The `.agent/skills/` directory contains documentation for:

| Skill | Purpose |
|-------|---------|
| `browser-use` | Official browser-use CLI reference |
| `browser-automation` | Playwright patterns & anti-detection |
| `agent-browser` | Vercel's agent-browser CLI |
| `computer-use-agents` | Vision-based AI agents |
| `workflow-automation` | Durable execution patterns |

## Security Notes

⚠️ **Ethical Use Only**

This bot is designed for:
- Automated testing
- Security research
- Authorized penetration testing

**Do NOT use for:**
- Creating spam accounts
- Fraud or impersonation
- Violating Terms of Service

## Troubleshooting

### Browser won't connect

```bash
# Check CDP URL format
echo $SBR_CDP_URL

# Test with simple navigation
python -c "
from browser_use import Browser, BrowserConfig
import asyncio
import os

async def test():
    b = Browser(config=BrowserConfig(cdp_url=os.getenv('SBR_CDP_URL')))
    await b.close()
    print('OK')

asyncio.run(test())
"
```

### CAPTCHA not solving

1. Check CapSolver balance: `python -c "from captcha_solver import *; ..."`
2. Verify site key extraction in prompts
3. Fall back to manual solving

### SMS not received

1. Check SMS-Activate balance
2. Try different country (Russia is cheapest)
3. Some services block virtual numbers

## License

MIT
