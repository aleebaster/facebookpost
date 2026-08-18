"""
Main entry point for Facebook Property Posting Bot.
Orchestrates the full publication workflow.
"""

import asyncio
import random
import sys
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from loguru import logger

from src.browser import BrowserManager
from src.facebook import FacebookHelper, FacebookState
from src.groups import GroupManager
from src.publisher import Publisher
from src.content_generator import ContentGenerator
from src.media import MediaManager
from src.database import PublicationLog


def setup_logging(config: dict):
    """Configure loguru logging."""
    log_config = config.get("logging", {})
    log_file = log_config.get("file", "logs/bot.log")
    log_level = log_config.get("level", "INFO")

    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(sys.stderr, level=log_level, colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>")
    logger.add(log_file, level=log_level, rotation="10 MB", retention="30 days",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}")


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


LOGIN_TIMEOUT_MINUTES = 60  # generous timeout for manual login


async def run_login_mode(config_path: str = "config.yaml"):
    """LOGIN mode: open Chrome, navigate to Facebook, wait for manual login."""
    load_dotenv()
    config = load_config(config_path)
    setup_logging(config)

    browser_config = config.get("browser", {})

    logger.info("")
    logger.info("=" * 60)
    logger.info("FACEBOOK LOGIN MODE")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Chrome Profile 2 is open.")
    logger.info("Facebook has been opened.")
    logger.info("")
    logger.info("Please log into Facebook MANUALLY in the Chrome window.")
    logger.info("Do NOT enter credentials through the bot.")
    logger.info("")
    logger.info("After you finish logging in, return to this console.")
    logger.info("The bot will check the Facebook session automatically.")
    logger.info("=" * 60)
    logger.info("")

    browser = BrowserManager(
        user_data_dir=browser_config.get("user_data_dir", ""),
        profile_name=browser_config.get("profile_name", "Profile 2"),
        chrome_binary=browser_config.get("chrome_binary", ""),
        headless=browser_config.get("headless", False),
        slow_mo=browser_config.get("slow_mo", 100),
    )

    try:
        logger.info("[LOGIN 1] Starting Chrome Profile 2...")
        page = await browser.start()

        logger.info("[LOGIN 2] Connected to Chrome via CDP")
        logger.info("[LOGIN 3] Opening Facebook...")
        fb_opened = await browser.open_facebook()

        if not fb_opened:
            logger.error("[LOGIN 3] Failed to open Facebook.")
            logger.error("Check that Chrome Profile 2 is not locked.")
            return

        logger.info("[LOGIN 4] Facebook loaded")

        # Check if already authenticated
        is_authenticated = await browser.check_facebook_auth()

        if is_authenticated:
            logger.info("[LOGIN 5] Facebook session: AUTHENTICATED")
            logger.info("")
            logger.info("=" * 60)
            logger.info("FACEBOOK LOGIN SUCCESS")
            logger.info("=" * 60)
            logger.info("")
            logger.info("Facebook session is already authenticated.")
            logger.info("Profile: Profile 2")
            logger.info("")
            logger.info("Session is available for future bot runs.")
            logger.info("No posts were published.")
            logger.info("=" * 60)
            return

        logger.info("[LOGIN 5] Facebook session: NOT AUTHENTICATED")
        logger.info("[LOGIN 6] Waiting for manual login...")
        logger.info("")
        logger.info("Log into Facebook in the Chrome window.")
        logger.info(f"Timeout: {LOGIN_TIMEOUT_MINUTES} minutes")
        logger.info("")

        # Wait for manual login
        logged_in = await browser.wait_for_login(
            timeout_minutes=LOGIN_TIMEOUT_MINUTES
        )

        if logged_in:
            logger.info("")
            logger.info("=" * 60)
            logger.info("FACEBOOK LOGIN SUCCESS")
            logger.info("=" * 60)
            logger.info("")
            logger.info("Facebook session is authenticated.")
            logger.info("Profile: Profile 2")
            logger.info("")
            logger.info("Session is available for future bot runs.")
            logger.info("You can now close the LOGIN mode.")
            logger.info("No posts were published.")
            logger.info("=" * 60)
        else:
            logger.error("")
            logger.error("=" * 60)
            logger.error("LOGIN TIMEOUT")
            logger.error("=" * 60)
            logger.error(f"Login was not completed within {LOGIN_TIMEOUT_MINUTES} minutes.")
            logger.error("Please try again with: python -m src.main --mode LOGIN")
            logger.error("=" * 60)

    except KeyboardInterrupt:
        logger.info("LOGIN mode stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await browser.stop()


async def run_bot(mode: str = "DRY_RUN", config_path: str = "config.yaml"):
    """Main bot execution loop."""
    # Load configuration
    load_dotenv()
    config = load_config(config_path)
    setup_logging(config)

    logger.info("=" * 60)
    logger.info("Facebook Property Posting Bot")
    logger.info(f"Mode: {mode}")
    logger.info("=" * 60)

    # Initialize components
    browser_config = config.get("browser", {})
    timing_config = config.get("timing", {})
    content_config = config.get("content", {})
    media_config = config.get("media", {})
    groups_config = config.get("groups", {})

    # Load groups
    group_manager = GroupManager(groups_config.get("file", "data/groups.txt"))
    if group_manager.count == 0:
        logger.error("No groups found! Add group URLs to data/groups.txt")
        return

    # Load media
    media_manager = MediaManager(
        photos_file=media_config.get("photos_file", "data/photos.txt"),
        videos_file=media_config.get("videos_file", "data/videos.txt"),
        photos_dir=media_config.get("photos_dir", "data/photos"),
        videos_dir=media_config.get("videos_dir", "data/videos"),
    )

    # Show media summary
    photos_dir = Path(media_config.get("photos_dir", "data/photos"))
    videos_dir = Path(media_config.get("videos_dir", "data/videos"))
    photo_count = len(media_manager.photos)
    video_count = len(media_manager.videos)

    logger.info(f"Photos directory:")
    logger.info(f"  {photos_dir.resolve()}")
    logger.info(f"Photos found: {photo_count}")
    logger.info(f"Videos directory:")
    logger.info(f"  {videos_dir.resolve()}")
    logger.info(f"Videos found: {video_count}")

    # Generate content variations
    content_generator = ContentGenerator(
        num_variations=content_config.get("number_of_variations", 6)
    )
    content_generator.generate()

    # Initialize database
    db_path = config.get("database", {}).get("path", "data/publications.db")
    database = PublicationLog(db_path)

    # Start browser
    browser = BrowserManager(
        user_data_dir=browser_config.get("user_data_dir", ""),
        profile_name=browser_config.get("profile_name", "Profile 2"),
        chrome_binary=browser_config.get("chrome_binary", ""),
        headless=browser_config.get("headless", False),
        slow_mo=browser_config.get("slow_mo", 100),
    )

    try:
        page = await browser.start()

        # Open Facebook - MUST succeed before proceeding
        fb_opened = await browser.open_facebook()
        if not fb_opened:
            logger.error("")
            logger.error("CRITICAL: Facebook was NOT opened.")
            logger.error("Cannot proceed without authenticated Facebook session.")
            logger.error("Stopping workflow.")
            return

        # Check if logged in - MUST succeed before proceeding
        is_logged_in = await browser.check_facebook_auth()

        if not is_logged_in:
            logger.error("")
            logger.error("=" * 60)
            logger.error("FACEBOOK SESSION NOT AUTHENTICATED")
            logger.error("=" * 60)
            logger.error("")
            logger.error("Please run:")
            logger.error("")
            logger.error("  python -m src.main --mode LOGIN")
            logger.error("")
            logger.error("Log into Facebook manually in the Chrome window.")
            logger.error("Then run your desired mode again.")
            logger.error("")
            logger.error("No posts were published.")
            logger.error("=" * 60)
            return

        # Both conditions met - safe to proceed
        logger.info(f"Facebook session: AUTHENTICATED")
        logger.info(f"Loaded {group_manager.count} group(s)")

        # Initialize publisher
        publisher = Publisher(
            page=page,
            database=database,
            content_generator=content_generator,
            media_manager=media_manager,
            timing_config=timing_config,
        )

        # Main publication loop
        max_failures = timing_config.get("max_consecutive_failures", 3)
        min_interval = timing_config.get("min_post_interval", 180)
        max_interval = timing_config.get("max_post_interval", 420)

        total = group_manager.count
        for i, group_url in enumerate(group_manager):
            group_num = i + 1

            # Log current working page before each group
            current_page_url = page.url
            logger.info("")
            logger.info("=" * 60)
            logger.info(f"[{group_num}/{total}]")
            logger.info(f"CURRENT WORKING PAGE: {current_page_url}")
            logger.info(f"Target group:")
            logger.info(f"  {group_url}")
            logger.info("=" * 60)

            # Check consecutive failures
            if publisher.consecutive_failures >= max_failures:
                logger.error(
                    f"Too many consecutive failures ({publisher.consecutive_failures}). "
                    "Stopping to protect your account."
                )
                break

            # Publish to group
            result = await publisher.publish_to_group(
                group_url,
                mode=mode,
                group_index=group_num,
                total_groups=total,
            )

            # Log result
            status_label = {
                "SUCCESS": "[OK]",
                "FAILED": "[FAIL]",
                "SKIPPED": "[SKIP]",
                "REQUIRES_MANUAL_ACTION": "[WARN]",
                "FACEBOOK_RESTRICTION": "[BLOCKED]",
            }
            label = status_label.get(result["status"], "[??]")
            logger.info(f"Result: {label} {result['status']}")
            if result["error"]:
                logger.info(f"Detail: {result['error']}")

            # Log current page after group processing
            logger.info(f"CURRENT WORKING PAGE: {page.url}")

            # Pause between groups (except after last group)
            if i < group_manager.count - 1:
                pause = random.randint(min_interval, max_interval)
                logger.info(f"Pausing {pause}s before next group...")
                await asyncio.sleep(pause)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await browser.stop()

    # Print summary
    stats = database.get_stats()
    logger.info("")
    logger.info("=" * 60)
    logger.info("Publication Summary:")
    for status, count in stats.items():
        logger.info(f"  {status}: {count}")
    logger.info("=" * 60)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Facebook Property Posting Bot")
    parser.add_argument(
        "--mode",
        choices=["LOGIN", "DRY_RUN", "MANUAL_APPROVAL", "AUTO"],
        default="DRY_RUN",
        help="Operating mode (default: DRY_RUN)",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )

    args = parser.parse_args()

    if args.mode == "LOGIN":
        asyncio.run(run_login_mode(config_path=args.config))
    else:
        asyncio.run(run_bot(mode=args.mode, config_path=args.config))


if __name__ == "__main__":
    main()
