# Goldone Trading Signal Bot

Free 24/7 trading signals via GitHub Actions + Telegram.

## Bots
- **forex_bot.py** — XAU/USD & EUR/USD — Weekdays Mon–Fri
- **crypto_bot.py** — BTC, ETH, BNB — Weekends Sat & Sun

## Setup Steps

### Step 1 — Fork or create this repo on GitHub

### Step 2 — Add Secrets
Go to: Settings → Secrets and variables → Actions → New repository secret

Add these 4 secrets:
| Name | Value |
|------|-------|
| TELEGRAM_TOKEN | your bot token from @BotFather |
| TELEGRAM_CHAT_ID | 8526718482 |
| TWELVE_DATA_KEY | your free key from twelvedata.com |
| GROQ_KEY | your free key from console.groq.com/keys |

### Step 3 — Enable Actions
Go to: Actions tab → Enable workflows

### Done!
- Forex signals every 20 min on weekdays
- Crypto signals every 30 min on weekends
- 100% Free — GitHub gives 2000 free minutes/month
