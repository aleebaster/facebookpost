# Facebook Property Posting Bot 🏠

Automated bot for posting property listings to Facebook groups using browser automation with Playwright.

## ⚠️ Safety Features

- **Uses your existing Chrome session** — no passwords stored
- **Never bypasses** CAPTCHA, security checks, or Facebook protections
- **Auto-stops** when Facebook shows any restriction or verification
- **Configurable delays** between actions to avoid triggering spam filters
- **Manual approval mode** — review every post before publishing

## Requirements

- Python 3.10+
- Google Chrome installed
- Facebook account (logged in Chrome)

## Installation

```bash
# Clone the repository
git clone https://github.com/aleebaster/facebookpost.git
cd facebookpost

# Create virtual environment
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate   # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (one-time)
playwright install chromium

# Copy and edit configuration
copy .env.example .env
```

## Configuration

### 1. Add Facebook Group URLs

Edit `data/groups.txt` — one URL per line:

```
https://www.facebook.com/groups/123456789
https://www.facebook.com/groups/realestate-burshytyn
```

### 2. Add Photo URLs

Edit `data/photos.txt` — one URL or local path per line:

```
https://example.com/house-photo-1.jpg
https://example.com/house-photo-2.jpg
C:\Users\You\Pictures\house.jpg
```

### 3. Add Video URLs

Edit `data/videos.txt` — one URL or local path per line:

```
https://example.com/house-tour.mp4
```

### 4. Configure Timing

Edit `config.yaml`:

```yaml
timing:
  min_post_interval: 180    # Minimum seconds between posts
  max_post_interval: 420    # Maximum seconds between posts
  page_load_delay: 5        # Seconds to wait after page load
  form_delay: 3             # Seconds before form interactions
  submit_delay: 5           # Seconds after submitting
```

### 5. Authorize Facebook

```bash
# First run — log in manually in the browser window
python -m src.main --mode DRY_RUN
```

The bot will open Chrome and navigate to Facebook. Log in manually. After login, the browser session is saved for future runs.

## Usage

### DRY_RUN Mode

Shows what would be published without actually posting:

```bash
python -m src.main --mode DRY_RUN
```

### MANUAL_APPROVAL Mode

Shows each post and waits for your confirmation:

```bash
python -m src.main --mode MANUAL_APPROVAL
```

Press `y` to publish, `n` to skip, `quit` to stop.

### AUTO Mode

Publishes automatically with built-in safety checks:

```bash
python -m src.main --mode AUTO
```

## Project Structure

```
facebookpost/
├── src/
│   ├── browser.py           # Chrome persistent profile management
│   ├── facebook.py          # Facebook navigation & safety checks
│   ├── groups.py            # Group list loading & validation
│   ├── publisher.py         # Core publication workflow
│   ├── content_generator.py # Text variation generator
│   ├── media.py             # Photo & video handling
│   ├── database.py          # SQLite publication log
│   └── main.py              # Main entry point
├── data/
│   ├── groups.txt           # Facebook group URLs
│   ├── photos.txt           # Photo URLs/paths
│   ├── videos.txt           # Video URLs/paths
│   └── publications.db      # Publication log (auto-created)
├── logs/                    # Log files
├── tests/                   # Tests
├── .env.example             # Environment template
├── config.yaml              # Main configuration
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## Publication Log

All publications are logged to `data/publications.db` (SQLite). View with:

```python
from src.database import PublicationLog

db = PublicationLog()
stats = db.get_stats()
print(stats)
```

### Status Types

- `SUCCESS` — Post published successfully
- `FAILED` — Publication failed
- `SKIPPED` — Group skipped (already published or no access)
- `REQUIRES_MANUAL_ACTION` — Facebook requires verification
- `FACEBOOK_RESTRICTION` — Facebook restriction detected

## ⚡ When the Bot Stops

The bot automatically stops and alerts you if:

- Facebook shows CAPTCHA or identity verification
- Account restrictions are detected
- Page behaves unexpectedly
- Multiple consecutive publication failures occur

**Never try to bypass these stops manually.**

## License

For personal use only. Respect Facebook's Terms of Service.
