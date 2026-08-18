"""
Publication workflow module.
Handles the actual posting process to Facebook groups.
"""

import asyncio
import random
from typing import Dict, Optional

from loguru import logger
from playwright.async_api import Page

from src.facebook import FacebookHelper, FacebookState
from src.content_generator import ContentGenerator
from src.media import MediaManager
from src.database import PublicationLog, PublicationStatus


class Publisher:
    """Handles the publication workflow for a single group."""

    def __init__(
        self,
        page: Page,
        database: PublicationLog,
        content_generator: ContentGenerator,
        media_manager: MediaManager,
        timing_config: Dict,
    ):
        self.page = page
        self.db = database
        self.content = content_generator
        self.media = media_manager
        self.timing = timing_config
        self.fb = FacebookHelper(page)

        # Tracking
        self._consecutive_failures = 0
        self._variation_index = 0

    async def publish_to_group(
        self,
        group_url: str,
        mode: str = "DRY_RUN",
        force: bool = False,
    ) -> Dict:
        """
        Attempt to publish a property listing to a Facebook group.

        Args:
            group_url: URL of the Facebook group
            mode: DRY_RUN, MANUAL_APPROVAL, or AUTO
            force: If True, publish even if previously successful

        Returns:
            Dictionary with publication result details
        """
        result = {
            "group_url": group_url,
            "group_name": None,
            "status": PublicationStatus.SKIPPED.value,
            "text_variation_index": self._variation_index,
            "post_url": None,
            "error": None,
        }

        try:
            # Step 1: Check if already published (unless forced)
            if not force and self.db.was_successful(group_url):
                logger.info(f"Already published to this group, skipping: {group_url}")
                result["status"] = PublicationStatus.SKIPPED.value
                result["error"] = "Already published previously"
                return result

            # Step 2: Navigate to group
            logger.info(f"Navigating to group: {group_url}")
            nav_ok = await self.fb.navigate_to(group_url)
            if not nav_ok:
                safety_state = await self.fb.check_safety()
                if safety_state != FacebookState.OK:
                    result["status"] = self._map_safety_state(safety_state)
                    result["error"] = f"Safety issue: {safety_state.value}"
                    self.db.log_publication(
                        group_url=group_url,
                        status=result["status"],
                        error_message=result["error"],
                    )
                    return result
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = "Failed to navigate to group"
                self.db.log_publication(
                    group_url=group_url,
                    status=PublicationStatus.FAILED.value,
                    error_message=result["error"],
                )
                return result

            # Step 3: Get group name
            group_name = await self.fb.get_group_name()
            result["group_name"] = group_name
            logger.info(f"Group name: {group_name or 'Unknown'}")

            # Step 4: Check if posting is allowed
            can_post = await self.fb.can_create_post()
            if not can_post:
                logger.warning(f"Cannot create post in this group: {group_url}")
                result["status"] = PublicationStatus.SKIPPED.value
                result["error"] = "Post creation not available in this group"
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=PublicationStatus.SKIPPED.value,
                    error_message=result["error"],
                )
                return result

            # Step 5: Check for Facebook errors
            has_error, error_text = await self.fb.check_for_errors()
            if has_error:
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = error_text
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=PublicationStatus.FAILED.value,
                    error_message=error_text,
                )
                return result

            # Step 6: Prepare content
            text = self.content.get_variation(self._variation_index)
            self._increment_variation()

            # Validate text
            validation_errors = self.content.validate_text(text)
            if validation_errors:
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = f"Content validation failed: {'; '.join(validation_errors)}"
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=PublicationStatus.FAILED.value,
                    error_message=result["error"],
                )
                return result

            # Step 7: Handle based on mode
            if mode == "DRY_RUN":
                return await self._dry_run(group_url, group_name, text, result)
            elif mode == "MANUAL_APPROVAL":
                return await self._manual_approval(group_url, group_name, text, result)
            elif mode == "AUTO":
                return await self._auto_publish(group_url, group_name, text, result)
            else:
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = f"Unknown mode: {mode}"
                return result

        except Exception as e:
            logger.error(f"Unexpected error publishing to {group_url}: {e}")
            self._consecutive_failures += 1
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = str(e)
            self.db.log_publication(
                group_url=group_url,
                group_name=result.get("group_name"),
                status=PublicationStatus.FAILED.value,
                error_message=str(e),
            )
            return result

    async def _dry_run(self, group_url, group_name, text, result):
        """DRY_RUN mode - show what would be published."""
        logger.info("=" * 50)
        logger.info(f"DRY RUN — Would publish to: {group_name or group_url}")
        logger.info(f"Text variation #{result['text_variation_index']}:")
        logger.info("-" * 30)
        logger.info(text)
        logger.info("-" * 30)
        if self.media.has_photos:
            logger.info(f"Photos: {len(self.media.photos)} file(s)")
        if self.media.has_videos:
            logger.info(f"Videos: {len(self.media.videos)} file(s)")
        logger.info("=" * 50)

        result["status"] = PublicationStatus.SUCCESS.value
        result["error"] = "DRY_RUN - no actual publication"

        self.db.log_publication(
            group_url=group_url,
            group_name=group_name,
            text_variation_index=result["text_variation_index"],
            text_preview=text[:500],
            photos_used=self.media.photos if self.media.has_photos else [],
            video_used=self.media.has_videos,
            status="SUCCESS",
            error_message="DRY_RUN",
        )

        self._consecutive_failures = 0
        return result

    async def _manual_approval(self, group_url, group_name, text, result):
        """MANUAL_APPROVAL mode - show content and wait for user confirmation."""
        logger.info("=" * 50)
        logger.info(f"MANUAL APPROVAL — Publish to: {group_name or group_url}")
        logger.info(f"Text variation #{result['text_variation_index']}:")
        logger.info("-" * 30)
        logger.info(text)
        logger.info("-" * 30)

        while True:
            response = input("\nPublish? (y/n/quit): ").strip().lower()
            if response in ("y", "yes"):
                break
            elif response in ("n", "no"):
                result["status"] = PublicationStatus.SKIPPED.value
                result["error"] = "Skipped by user"
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    text_variation_index=result["text_variation_index"],
                    text_preview=text[:500],
                    status=PublicationStatus.SKIPPED.value,
                    error_message="Skipped by user",
                )
                return result
            elif response in ("quit", "q"):
                raise KeyboardInterrupt("User requested quit")
            else:
                logger.info("Please enter y (yes), n (no), or quit")

        # Proceed with publication
        return await self._actual_publish(group_url, group_name, text, result)

    async def _auto_publish(self, group_url, group_name, text, result):
        """AUTO mode - publish automatically."""
        return await self._actual_publish(group_url, group_name, text, result)

    async def _actual_publish(self, group_url, group_name, text, result):
        """Actually perform the publication to Facebook."""
        try:
            # Click "Create a post" button
            clicked = await self.fb.click_create_post()
            if not clicked:
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = "Could not click 'Create a post' button"
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    text_variation_index=result["text_variation_index"],
                    text_preview=text[:500],
                    status=PublicationStatus.FAILED.value,
                    error_message=result["error"],
                )
                return result

            await asyncio.sleep(self.timing.get("form_delay", 3))

            # Safety check after clicking
            safety = await self.fb.check_safety()
            if safety != FacebookState.OK:
                result["status"] = self._map_safety_state(safety)
                result["error"] = f"Safety issue after opening form: {safety.value}"
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=result["status"],
                    error_message=result["error"],
                )
                return result

            # Type the post text
            text_typed = await self._type_post_text(text)
            if not text_typed:
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = "Could not type post text"
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=PublicationStatus.FAILED.value,
                    error_message=result["error"],
                )
                return result

            # Attach media if available
            photos_attached = False
            if self.media.has_photos:
                photos_attached = await self._attach_photos()

            videos_attached = False
            if self.media.has_videos:
                videos_attached = await self._attach_videos()

            await asyncio.sleep(self.timing.get("form_delay", 3))

            # Final safety check before posting
            safety = await self.fb.check_safety()
            if safety != FacebookState.OK:
                result["status"] = self._map_safety_state(safety)
                result["error"] = f"Safety issue before submit: {safety.value}"
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=result["status"],
                    error_message=result["error"],
                )
                return result

            # Click Post button
            posted = await self._click_post_button()
            if not posted:
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = "Could not click 'Post' button"
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=PublicationStatus.FAILED.value,
                    error_message=result["error"],
                )
                return result

            # Wait and check result
            await asyncio.sleep(self.timing.get("submit_delay", 5))

            # Final safety check
            safety = await self.fb.check_safety()
            if safety != FacebookState.OK:
                result["status"] = self._map_safety_state(safety)
                result["error"] = f"Safety issue after posting: {safety.value}"
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=result["status"],
                    error_message=result["error"],
                )
                return result

            # Success!
            result["status"] = PublicationStatus.SUCCESS.value
            result["error"] = None
            self._consecutive_failures = 0

            self.db.log_publication(
                group_url=group_url,
                group_name=group_name,
                text_variation_index=result["text_variation_index"],
                text_preview=text[:500],
                photos_used=self.media.photos if photos_attached else [],
                video_used=videos_attached,
                status=PublicationStatus.SUCCESS.value,
                post_url=result["post_url"],
            )

            logger.info(f"Successfully published to: {group_name or group_url}")
            return result

        except Exception as e:
            logger.error(f"Error during actual publication: {e}")
            self._consecutive_failures += 1
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = str(e)
            self.db.log_publication(
                group_url=group_url,
                group_name=group_name,
                status=PublicationStatus.FAILED.value,
                error_message=str(e),
            )
            return result

    async def _type_post_text(self, text: str) -> bool:
        """Type text into the post creation form."""
        # Look for the contenteditable div or textarea in the post form
        selectors = [
            'div[role="textbox"][contenteditable="true"]',
            'div[contenteditable="true"][data-lexical-editor="true"]',
            'div[contenteditable="true"]',
            'textarea[aria-label*="Write"]',
            'textarea[aria-label*="Напишіть"]',
        ]

        for selector in selectors:
            try:
                element = await self.page.wait_for_selector(selector, timeout=5000)
                if element:
                    await element.click()
                    await asyncio.sleep(0.5)
                    # Type text using keyboard to work with contenteditable
                    await self.page.keyboard.type(text, delay=10)
                    logger.info("Post text typed successfully")
                    return True
            except Exception:
                continue

        logger.warning("Could not find post text input field")
        return False

    async def _attach_photos(self) -> bool:
        """Attach photos to the post."""
        try:
            # Find the photo upload button
            photo_selectors = [
                'input[accept*="image"]',
                'input[accept*="photo"]',
                'input[type="file"][accept*="image"]',
                'div[aria-label*="Photo"] input[type="file"]',
                'div[aria-label*="Фото"] input[type="file"]',
            ]

            for selector in photo_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        # Upload photos
                        for photo_url in self.media.photos:
                            await element.set_input_files(photo_url)
                            await asyncio.sleep(2)
                        logger.info(f"Attached {len(self.media.photos)} photo(s)")
                        return True
                except Exception:
                    continue

            logger.warning("Could not find photo upload input")
            return False
        except Exception as e:
            logger.error(f"Error attaching photos: {e}")
            return False

    async def _attach_videos(self) -> bool:
        """Attach videos to the post."""
        try:
            video_selectors = [
                'input[accept*="video"]',
                'input[type="file"][accept*="video"]',
                'div[aria-label*="Video"] input[type="file"]',
                'div[aria-label*="Відео"] input[type="file"]',
            ]

            for selector in video_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        for video_url in self.media.videos:
                            await element.set_input_files(video_url)
                            await asyncio.sleep(3)
                        logger.info(f"Attached {len(self.media.videos)} video(s)")
                        return True
                except Exception:
                    continue

            logger.warning("Could not find video upload input")
            return False
        except Exception as e:
            logger.error(f"Error attaching videos: {e}")
            return False

    async def _click_post_button(self) -> bool:
        """Click the final 'Post' / 'Опублікувати' button."""
        post_selectors = [
            'div[role="button"]:has-text("Post")',
            'div[role="button"]:has-text("Опублікувати")',
            'div[role="button"]:has-text("Поділитися")',
            'button:has-text("Post")',
            'button:has-text("Опублікувати")',
            '[aria-label="Post"]',
            '[aria-label="Опублікувати"]',
        ]

        for selector in post_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    # Check if button is enabled
                    disabled = await element.get_attribute("aria-disabled")
                    if disabled == "true":
                        logger.warning("Post button is disabled")
                        return False

                    await element.click()
                    logger.info("Post button clicked")
                    return True
            except Exception:
                continue

        logger.warning("Could not find Post button")
        return False

    def _map_safety_state(self, state: FacebookState) -> str:
        """Map Facebook safety state to publication status."""
        mapping = {
            FacebookState.CAPTCHA: PublicationStatus.FACEBOOK_RESTRICTION.value,
            FacebookState.CHECKPOINT: PublicationStatus.REQUIRES_MANUAL_ACTION.value,
            FacebookState.RESTRICTION: PublicationStatus.FACEBOOK_RESTRICTION.value,
            FacebookState.LOGIN_REQUIRED: PublicationStatus.REQUIRES_MANUAL_ACTION.value,
            FacebookState.UNKNOWN: PublicationStatus.REQUIRES_MANUAL_ACTION.value,
        }
        return mapping.get(state, PublicationStatus.FAILED.value)

    def _increment_variation(self):
        """Increment the text variation index."""
        num = len(self.content._generated) if self.content._generated else 6
        self._variation_index = (self._variation_index + 1) % num

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def reset_failures(self):
        self._consecutive_failures = 0
