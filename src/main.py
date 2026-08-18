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

    logger.info(f"Loaded {group_manager.count} group(s)")

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
    logger.info(f"Photos directory:")
    logger.info(f"  {photos_dir.resolve()}")
    logger.info(f"Videos directory:")
    logger.info(f"  {videos_dir.resolve()}")
    photo_count = len(media_manager.photos)
    video_count = len(media_manager.videos)
    logger.info(f"Photos found: {photo_count}")
    logger.info(f"Videos found: {video_count}")

    # Generate content variations
    content_generator = ContentGenerator(
        num_variations=content_config.get("number_of_variations", 6)
    )
    content_generator.generate()
    logger.info(f"Generated {len(content_generator._generated)} text variations")

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

        # Open Facebook
        fb_opened = await browser.open_facebook()
        if not fb_opened:
            logger.error("Failed to open Facebook. Exiting.")
            return

        # Check if logged in
        is_logged_in = await browser.check_facebook_auth()

        if not is_logged_in:
            logger.warning("Not logged into Facebook!")
            if mode in ("MANUAL_APPROVAL", "AUTO"):
                logger.info("Please log into Facebook in the browser window...")
                logged_in = await browser.wait_for_login(timeout_minutes=5)
                if not logged_in:
                    logger.error("Login timeout. Exiting.")
                    return
            else:
                logger.error(
                    "Facebook session is not authenticated in Chrome Profile 2.\n"
                    "Please log into Facebook manually in Chrome Profile 2 "
                    "and run the bot again."
                )
                return

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
            logger.info("")
            logger.info("=" * 60)
            logger.info(f"[{group_num}/{total}]")
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
        choices=["DRY_RUN", "MANUAL_APPROVAL", "AUTO"],
        default="DRY_RUN",
        help="Operating mode (default: DRY_RUN)",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )

    args = parser.parse_args()
    asyncio.run(run_bot(mode=args.mode, config_path=args.config))


if __name__ == "__main__":
    main()
