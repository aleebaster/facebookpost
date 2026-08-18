"""
Publication workflow module.
Handles the actual posting process to Facebook groups.
"""

import asyncio
import random
from typing import Dict, Optional, Tuple

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
        group_index: int = 0,
        total_groups: int = 1,
        force: bool = False,
    ) -> Dict:
        """
        Attempt to publish a property listing to a Facebook group.

        Args:
            group_url: URL of the Facebook group
            mode: DRY_RUN, MANUAL_APPROVAL, or AUTO
            group_index: Current group number (1-based)
            total_groups: Total number of groups
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
            # Step 1: Check if already published (skip in DRY_RUN to allow navigation test)
            if mode != "DRY_RUN" and not force and self.db.was_successful(group_url):
                logger.info(f"Already published to this group, skipping: {group_url}")
                result["status"] = PublicationStatus.SKIPPED.value
                result["error"] = "Already published previously"
                return result

            # Step 2: Navigate to group
            nav_ok, current_url = await self.fb.navigate_to(group_url)

            if not nav_ok:
                # Check if we're on about:blank
                if current_url == "about:blank":
                    result["status"] = PublicationStatus.FAILED.value
                    result["error"] = "NAVIGATION_FAILED - browser is on about:blank"
                    logger.error(f"Navigation FAILED")
                    logger.error(f"Target URL: {group_url}")
                    logger.error(f"Current URL: {current_url}")
                    self.db.log_publication(
                        group_url=group_url,
                        status=PublicationStatus.FAILED.value,
                        error_message=result["error"],
                    )
                    return result

                # Check for safety issues
                safety_state = await self.fb.check_safety()
                if safety_state != FacebookState.OK:
                    result["status"] = self._map_safety_state(safety_state)
                    result["error"] = f"Safety issue: {safety_state.value}"
                    logger.error(f"Navigation FAILED - safety issue: {safety_state.value}")
                    logger.error(f"Target URL: {group_url}")
                    logger.error(f"Current URL: {current_url}")
                    self.db.log_publication(
                        group_url=group_url,
                        status=result["status"],
                        error_message=result["error"],
                    )
                    return result

                result["status"] = PublicationStatus.FAILED.value
                result["error"] = f"Navigation failed. Current URL: {current_url}"
                logger.error(f"Navigation FAILED")
                logger.error(f"Target URL: {group_url}")
                logger.error(f"Current URL: {current_url}")
                self.db.log_publication(
                    group_url=group_url,
                    status=PublicationStatus.FAILED.value,
                    error_message=result["error"],
                )
                return result

            # Navigation succeeded
            logger.info(f"Group navigation: SUCCESS")

            # Verify we're actually on a Facebook group page
            if "facebook.com/groups/" not in current_url.lower():
                logger.warning(f"Current URL is not a group page: {current_url}")

            # Step 3: Get group name
            group_name = await self.fb.get_group_name()
            result["group_name"] = group_name
            if group_name:
                logger.info(f"Group name: {group_name}")

            # Step 4: Check if posting is allowed
            can_post = await self.fb.can_create_post()
            if not can_post:
                logger.warning(f"Cannot create post in this group")
                result["status"] = PublicationStatus.SKIPPED.value
                result["error"] = "Post creation not available in this group"
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=PublicationStatus.SKIPPED.value,
                    error_message=result["error"],
                )
                return result

            logger.info("Post creation: AVAILABLE")

            # Step 5: Check for Facebook errors
            has_error, error_text = await self.fb.check_for_errors()
            if has_error:
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = error_text
                logger.error(f"Facebook error: {error_text[:200]}")
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
                logger.error(f"Content validation failed: {validation_errors}")
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=PublicationStatus.FAILED.value,
                    error_message=result["error"],
                )
                return result

            logger.info("Content validation: OK")

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
        """DRY_RUN mode - show what would be published, no actual posting."""
        logger.info(f"Mode: DRY_RUN")

        # Media check
        photo_count = len(self.media.photos) if self.media.has_photos else 0
        video_count = len(self.media.videos) if self.media.has_videos else 0
        logger.info(f"Media check: OK")
        logger.info(f"Photos: {photo_count}")
        logger.info(f"Videos: {video_count}")

        # Show text preview
        logger.info(f"Text variation #{result['text_variation_index']}:")
        logger.info("-" * 30)
        # Log first 3 lines of text as preview
        text_lines = text.strip().split("\n")
        for line in text_lines[:5]:
            logger.info(f"  {line}")
        if len(text_lines) > 5:
            logger.info(f"  ... ({len(text_lines)} lines total)")
        logger.info("-" * 30)

        logger.info(f"Publishing: SKIPPED (DRY_RUN)")

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
        logger.info(f"Mode: MANUAL_APPROVAL")
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

        return await self._actual_publish(group_url, group_name, text, result)

    async def _auto_publish(self, group_url, group_name, text, result):
        """AUTO mode - publish automatically."""
        return await self._actual_publish(group_url, group_name, text, result)

    async def _find_composer_dialog(self):
        """Find and return the active composer dialog locator.

        After clicking 'Create a post', Facebook opens a modal dialog.
        We must scope ALL subsequent actions to this dialog to avoid
        scrolling the feed or interacting with elements outside the composer.
        """
        dialog_selectors = [
            '[role="dialog"]',
            '[aria-label="Create a post"]',
            '[aria-label="\u0421\u0442\u0432\u043e\u0440\u0438\u0442\u0438 \u0434\u043e\u043f\u0438\u0441"]',
        ]

        for selector in dialog_selectors:
            try:
                dialogs = self.page.locator(selector)
                count = await dialogs.count()
                if count > 0:
                    # Use the last visible dialog (most recent one opened)
                    dialog = dialogs.last
                    is_visible = await dialog.is_visible()
                    if is_visible:
                        logger.info(f"Post composer dialog detected: YES")
                        logger.info(f"Dialog count: {count}")
                        logger.info(f"Dialog selector: {selector}")
                        return dialog
            except Exception:
                continue

        logger.warning("No post composer dialog found")
        return None

    async def _actual_publish(self, group_url, group_name, text, result):
        """Actually perform the publication to Facebook.

        All post-composer actions (text, photo, video, publish) are scoped
        to the dialog locator to prevent feed scrolling.
        """
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

            # ========================================================
            # Find the active composer dialog.
            # From this point, ALL locators are scoped to the dialog.
            # No page-level scrolling or feed interaction is allowed.
            # ========================================================
            dialog = await self._find_composer_dialog()
            if dialog is None:
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = "Post composer dialog not found after clicking create"
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=PublicationStatus.FAILED.value,
                    error_message=result["error"],
                )
                return result

            logger.info("")
            logger.info("POST COMPOSER")
            logger.info("-" * 40)
            logger.info(f"Dialog detected: YES")

            # Verify dialog is still visible before each action
            if not await dialog.is_visible():
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = "Post composer dialog disappeared"
                logger.error("Post composer dialog disappeared unexpectedly.")
                logger.error("Stopping publication workflow.")
                return result

            # Type the post text — scoped to dialog
            text_typed = await self._type_post_text_in_dialog(dialog, text)
            if not text_typed:
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = "Could not type post text in composer"
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=PublicationStatus.FAILED.value,
                    error_message=result["error"],
                )
                return result

            # Attach media — scoped to dialog
            photos_attached = False
            if self.media.has_photos:
                photos_attached = await self._attach_photos_in_dialog(dialog)

            videos_attached = False
            if self.media.has_videos:
                videos_attached = await self._attach_videos_in_dialog(dialog)

            logger.info("-" * 40)

            await asyncio.sleep(self.timing.get("form_delay", 3))

            # Verify dialog is still visible before final check
            if not await dialog.is_visible():
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = "Post composer dialog disappeared before submit"
                logger.error("Post composer dialog disappeared before submit.")
                return result

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

            # Click Post button — scoped to dialog
            posted = await self._click_post_button_in_dialog(dialog)
            if not posted:
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = "Could not click 'Post' button in composer"
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=PublicationStatus.FAILED.value,
                    error_message=result["error"],
                )
                return result

            logger.info("Ready to publish: YES")

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

            logger.info(f"Publication SUCCESS — {group_name or group_url}")
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

    async def _type_post_text_in_dialog(self, dialog, text: str) -> bool:
        """Type text into the post creation form inside the dialog."""
        # Text input selectors — scoped to dialog
        selectors = [
            'div[role="textbox"][contenteditable="true"]',
            'div[contenteditable="true"][data-lexical-editor="true"]',
            'div[contenteditable="true"]',
            'textarea[aria-label*="Write"]',
            'textarea[aria-label*="\u041d\u0430\u043f\u0438\u0448\u0456\u0442\u044c"]',
        ]

        for selector in selectors:
            try:
                element = dialog.locator(selector).first
                count = await dialog.locator(selector).count()
                if count > 0 and await element.is_visible():
                    await element.click()
                    await asyncio.sleep(0.5)
                    # Use keyboard.type to avoid page-level scrolling
                    await self.page.keyboard.type(text, delay=10)
                    logger.info(f"Text field found: OK")
                    logger.info(f"Text entry: SUCCESS")
                    return True
            except Exception:
                continue

        logger.warning("Could not find post text input field inside dialog")
        return False

    async def _attach_photos_in_dialog(self, dialog) -> bool:
        """Attach photos to the post inside the dialog."""
        try:
            photo_selectors = [
                'input[accept*="image"]',
                'input[accept*="photo"]',
                'input[type="file"][accept*="image"]',
                'div[aria-label*="Photo"] input[type="file"]',
                'div[aria-label*="\u0424\u043e\u0442\u043e"] input[type="file"]',
            ]

            for selector in photo_selectors:
                try:
                    elements = dialog.locator(selector)
                    count = await elements.count()
                    if count > 0:
                        element = elements.first
                        for photo_url in self.media.photos:
                            await element.set_input_files(photo_url)
                            await asyncio.sleep(2)
                        logger.info(f"Photos attached: {len(self.media.photos)}")
                        return True
                except Exception:
                    continue

            # Fallback: search page for file inputs (hidden ones may be outside dialog)
            try:
                page_inputs = self.page.locator('input[type="file"][accept*="image"]')
                count = await page_inputs.count()
                if count > 0:
                    element = page_inputs.first
                    for photo_url in self.media.photos:
                        await element.set_input_files(photo_url)
                        await asyncio.sleep(2)
                    logger.info(f"Photos attached (page-level fallback): {len(self.media.photos)}")
                    return True
            except Exception:
                pass

            logger.warning("Could not find photo upload input in dialog")
            return False
        except Exception as e:
            logger.error(f"Error attaching photos: {e}")
            return False

    async def _attach_videos_in_dialog(self, dialog) -> bool:
        """Attach videos to the post inside the dialog."""
        try:
            video_selectors = [
                'input[accept*="video"]',
                'input[type="file"][accept*="video"]',
                'div[aria-label*="Video"] input[type="file"]',
                'div[aria-label*="\u0412\u0456\u0434\u0435\u043e"] input[type="file"]',
            ]

            for selector in video_selectors:
                try:
                    elements = dialog.locator(selector)
                    count = await elements.count()
                    if count > 0:
                        element = elements.first
                        for video_url in self.media.videos:
                            await element.set_input_files(video_url)
                            await asyncio.sleep(3)
                        logger.info(f"Videos attached: {len(self.media.videos)}")
                        return True
                except Exception:
                    continue

            # Fallback: search page for file inputs
            try:
                page_inputs = self.page.locator('input[type="file"][accept*="video"]')
                count = await page_inputs.count()
                if count > 0:
                    element = page_inputs.first
                    for video_url in self.media.videos:
                        await element.set_input_files(video_url)
                        await asyncio.sleep(3)
                    logger.info(f"Videos attached (page-level fallback): {len(self.media.videos)}")
                    return True
            except Exception:
                pass

            logger.warning("Could not find video upload input in dialog")
            return False
        except Exception as e:
            logger.error(f"Error attaching videos: {e}")
            return False

    async def _click_post_button_in_dialog(self, dialog) -> bool:
        """Click the final 'Post' / 'Publish' button inside the dialog."""
        post_selectors = [
            'div[role="button"]:has-text("Post")',
            'div[role="button"]:has-text("\u041e\u043f\u0443\u0431\u043b\u0456\u043a\u0443\u0432\u0430\u0442\u0438")',
            'div[role="button"]:has-text("\u041f\u043e\u0434\u0456\u043b\u0438\u0442\u0438\u0441\u044f")',
            'button:has-text("Post")',
            'button:has-text("\u041e\u043f\u0443\u0431\u043b\u0456\u043a\u0443\u0432\u0430\u0442\u0438")',
            '[aria-label="Post"]',
            '[aria-label="\u041e\u043f\u0443\u0431\u043b\u0456\u043a\u0443\u0432\u0430\u0442\u0438"]',
        ]

        for selector in post_selectors:
            try:
                elements = dialog.locator(selector)
                count = await elements.count()
                if count > 0:
                    # Find the publish button (not other buttons in the dialog)
                    for idx in range(count):
                        element = elements.nth(idx)
                        if await element.is_visible():
                            disabled = await element.get_attribute("aria-disabled")
                            if disabled == "true":
                                logger.warning("Post button is disabled")
                                return False

                            await element.click()
                            logger.info("Publish clicked")
                            return True
            except Exception:
                continue

        # Fallback: try page-level search for publish button
        try:
            page_buttons = self.page.locator('[aria-label="\u041e\u043f\u0443\u0431\u043b\u0456\u043a\u0443\u0432\u0430\u0442\u0438"]')
            count = await page_buttons.count()
            if count > 0:
                element = page_buttons.first
                if await element.is_visible():
                    await element.click()
                    logger.info("Publish clicked (page-level fallback)")
                    return True
        except Exception:
            pass

        logger.warning("Could not find Post button in dialog")
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
