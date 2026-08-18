# Facebook Property Posting Bot

Automated bot for posting property listings to Facebook groups using browser automation with Playwright.

## Safety Features

- **Uses your existing Chrome session** — no passwords stored
- **Never bypasses** CAPTCHA, security checks, or Facebook protections
- **Auto-stops** when Facebook shows any restriction or verification
- **Configurable delays** between actions to avoid triggering spam filters
- **Manual approval mode** — review every post before publishing

## Requirements

- Python 3.10+
- Google Chrome installed (system Chrome, not Playwright Chromium)
- Facebook account logged in within Chrome Profile 2

## Installation

```bash
# Clone the repository
git clone https://github.com/aleebaster/facebookpost.git
cd facebookpost

# Create virtual environment
python -m venv venv
venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (required for automation)
playwright install chromium

# Copy and edit configuration
copy .env.example .env
```

## Chrome Profile Setup

The bot uses your **existing Chrome Profile 2** where you are already logged into Facebook.

**Do NOT** log into Facebook through the bot. The bot reads your existing session.

### Configuration

In `config.yaml`:

```yaml
browser:
  user_data_dir: "C:\Users\andre\AppData\Local\Google\Chrome\User Data"
  profile_name: "Profile 2"
```

### IMPORTANT: Close Chrome Before Running

Playwright cannot access a Chrome profile that is already open in Chrome.

**Before running the bot:**
1. Close ALL Chrome windows that use Profile 2
2. Then run the bot
3. After the bot finishes, you can reopen Chrome normally

If you see: `Chrome profile is currently locked by another Chrome instance!`
- Close Chrome with Profile 2 and try again

## Adding Property Photos and Videos

**The simplest way** — copy files directly into the project folders:

### Photos

```
C:\AI\facebookpost\data\photos\
```

Supported formats: `.jpg`, `.jpeg`, `.png`, `.webp`

Example:
```
data/photos/
  ├── house1.jpg
  ├── house2.jpg
  ├── house3.jpg
  └── yard.jpg
```

### Videos

```
C:\AI\facebookpost\data\videos\
```

Supported formats: `.mp4`, `.mov`, `.webm`

Example:
```
data/videos/
  └── house-tour.mp4
```

The bot automatically detects all media files in these folders on startup:

```
Photos found: 4
Videos found: 1
```

### Legacy: URL Files

You can also add photo/video URLs in text files:
- `data/photos.txt` — one URL per line
- `data/videos.txt` — one URL per line

The bot loads from **both** local folders and URL files.

## Configuration

### Add Facebook Group URLs

Edit `data/groups.txt` — one URL per line:

```
https://www.facebook.com/groups/123456789
https://www.facebook.com/groups/realestate-burshytyn
```

### Configure Timing

Edit `config.yaml`:

```yaml
timing:
  min_post_interval: 180    # Minimum seconds between posts
  max_post_interval: 420    # Maximum seconds between posts
  page_load_delay: 5        # Seconds to wait after page load
  form_delay: 3             # Seconds before form interactions
  submit_delay: 5           # Seconds after submitting
```

## Usage

### DRY_RUN Mode

Tests the full workflow (navigation, group checks, content preparation) but does NOT publish:

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
│   ├── photos/              # Put your photos here
│   │   └── .gitkeep
│   ├── videos/              # Put your videos here
│   │   └── .gitkeep
│   ├── photos.txt           # Legacy: photo URLs
│   ├── videos.txt           # Legacy: video URLs
│   └── publications.db      # Publication log (auto-created)
├── logs/                    # Log files
├── tests/                   # Tests
├── .env.example             # Environment template
├── config.yaml              # Main configuration
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## Publication Log

All publications are logged to `data/publications.db` (SQLite).

### Status Types

- `SUCCESS` — Post published successfully
- `FAILED` — Publication failed
- `SKIPPED` — Group skipped (already published or no access)
- `REQUIRES_MANUAL_ACTION` — Facebook requires verification
- `FACEBOOK_RESTRICTION` — Facebook restriction detected

## When the Bot Stops

The bot automatically stops and alerts you if:

- Facebook shows CAPTCHA or identity verification
- Account restrictions are detected
- Page behaves unexpectedly
- Multiple consecutive publication failures occur

**Never try to bypass these stops manually.**

## License

For personal use only. Respect Facebook's Terms of Service.
