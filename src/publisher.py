"""
Publication workflow module with explicit state machine.

States:
  GROUP_OPENED
  COMPOSER_OPENED
  TEXT_ENTERED
  PHOTOS_ATTACHED
  VIDEO_ATTACHED
  READY_TO_PUBLISH
  PUBLISH_CLICKED
  PUBLICATION_CONFIRMED
  DRY_RUN_VALIDATED
  FAILED
"""

import asyncio
import random
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Tuple

from loguru import logger
from playwright.async_api import Page

from src.facebook import FacebookHelper, FacebookState
from src.content_generator import ContentGenerator
from src.media import MediaManager
from src.database import PublicationLog, PublicationStatus


class ComposerState(Enum):
    """Explicit state machine for post publication."""
    GROUP_OPENED = "GROUP_OPENED"
    COMPOSER_OPENED = "COMPOSER_OPENED"
    TEXT_ENTERED = "TEXT_ENTERED"
    PHOTOS_ATTACHED = "PHOTOS_ATTACHED"
    VIDEO_ATTACHED = "VIDEO_ATTACHED"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    PUBLISH_CLICKED = "PUBLISH_CLICKED"
    PUBLICATION_CONFIRMED = "PUBLICATION_CONFIRMED"
    DRY_RUN_VALIDATED = "DRY_RUN_VALIDATED"
    FAILED = "FAILED"


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

    def can_proceed_to_next_group(self, state: ComposerState, mode: str) -> bool:
        """Only allow next group if current operation fully completed.

        DRY_RUN: DRY_RUN_VALIDATED is sufficient.
        MANUAL_APPROVAL / AUTO: Only PUBLICATION_CONFIRMED.
        FAILED: never.
        """
        if state == ComposerState.FAILED:
            return False
        if mode == "DRY_RUN" and state == ComposerState.DRY_RUN_VALIDATED:
            return True
        if state == ComposerState.PUBLICATION_CONFIRMED:
            return True
        return False

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

        Returns a dict with result details and the final ComposerState.
        """
        state = ComposerState.GROUP_OPENED
        result = {
            "group_url": group_url,
            "group_name": None,
            "status": PublicationStatus.SKIPPED.value,
            "text_variation_index": self._variation_index,
            "post_url": None,
            "error": None,
            "composer_state": state,
        }

        try:
            # Step 1: Check if already published (skip in DRY_RUN to allow navigation test)
            if mode != "DRY_RUN" and not force and self.db.was_successful(group_url):
                logger.info(f"[POST] Already published to this group, skipping: {group_url}")
                result["status"] = PublicationStatus.SKIPPED.value
                result["error"] = "Already published previously"
                result["composer_state"] = ComposerState.FAILED
                return result

            # Step 2: Navigate to group
            nav_ok, current_url = await self.fb.navigate_to(group_url)

            if not nav_ok:
                if current_url == "about:blank":
                    result["status"] = PublicationStatus.FAILED.value
                    result["error"] = "NAVIGATION_FAILED - browser is on about:blank"
                    result["composer_state"] = ComposerState.FAILED
                    logger.error("[POST] Navigation FAILED - about:blank")
                    self.db.log_publication(
                        group_url=group_url,
                        status=PublicationStatus.FAILED.value,
                        error_message=result["error"],
                    )
                    return result

                safety_state = await self.fb.check_safety()
                if safety_state != FacebookState.OK:
                    result["status"] = self._map_safety_state(safety_state)
                    result["error"] = f"Safety issue: {safety_state.value}"
                    result["composer_state"] = ComposerState.FAILED
                    logger.error(f"[POST] Navigation FAILED - safety: {safety_state.value}")
                    self.db.log_publication(
                        group_url=group_url,
                        status=result["status"],
                        error_message=result["error"],
                    )
                    return result

                result["status"] = PublicationStatus.FAILED.value
                result["error"] = f"Navigation failed. Current URL: {current_url}"
                result["composer_state"] = ComposerState.FAILED
                logger.error(f"[POST] Navigation FAILED: {current_url}")
                self.db.log_publication(
                    group_url=group_url,
                    status=PublicationStatus.FAILED.value,
                    error_message=result["error"],
                )
                return result

            logger.info("[POST] Group navigation: SUCCESS")

            if "facebook.com/groups/" not in current_url.lower():
                logger.warning(f"[POST] Current URL is not a group page: {current_url}")

            # Step 3: Get group name
            group_name = await self.fb.get_group_name()
            result["group_name"] = group_name
            if group_name:
                logger.info(f"[POST] Group name: {group_name}")

            # Step 4: Check if posting is allowed
            can_post = await self.fb.can_create_post()
            if not can_post:
                logger.warning("[POST] Cannot create post in this group")
                result["status"] = PublicationStatus.SKIPPED.value
                result["error"] = "Post creation not available in this group"
                result["composer_state"] = ComposerState.FAILED
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=PublicationStatus.SKIPPED.value,
                    error_message=result["error"],
                )
                return result

            logger.info("[POST] Post creation: AVAILABLE")

            # Step 5: Check for Facebook errors
            has_error, error_text = await self.fb.check_for_errors()
            if has_error:
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = error_text
                result["composer_state"] = ComposerState.FAILED
                logger.error(f"[POST] Facebook error: {error_text[:200]}")
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

            validation_errors = self.content.validate_text(text)
            if validation_errors:
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = f"Content validation failed: {'; '.join(validation_errors)}"
                result["composer_state"] = ComposerState.FAILED
                logger.error(f"[POST] Content validation failed: {validation_errors}")
                self.db.log_publication(
                    group_url=group_url,
                    group_name=group_name,
                    status=PublicationStatus.FAILED.value,
                    error_message=result["error"],
                )
                return result

            logger.info("[POST] Content validation: OK")

            # Step 7: Open composer — shared across all modes
            state, result = await self._open_composer(group_url, group_name, text, result, mode)
            if state == ComposerState.FAILED:
                return result

            # Step 8: Enter text
            state, result = await self._enter_text(dialog=None, text=text, result=result)
            if state == ComposerState.FAILED:
                return result

            # Step 9: Attach media
            state, result = await self._attach_media(dialog=None, result=result)
            if state == ComposerState.FAILED:
                return result

            # Step 10: Handle based on mode
            if mode == "DRY_RUN":
                return await self._dry_run(group_url, group_name, text, result)
            elif mode == "MANUAL_APPROVAL":
                return await self._manual_approval(group_url, group_name, text, result)
            elif mode == "AUTO":
                return await self._auto_publish(group_url, group_name, text, result)
            else:
                result["status"] = PublicationStatus.FAILED.value
                result["error"] = f"Unknown mode: {mode}"
                result["composer_state"] = ComposerState.FAILED
                return result

        except Exception as e:
            logger.error(f"[POST] Unexpected error publishing to {group_url}: {e}")
            self._consecutive_failures += 1
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = str(e)
            result["composer_state"] = ComposerState.FAILED
            self.db.log_publication(
                group_url=group_url,
                group_name=result.get("group_name"),
                status=PublicationStatus.FAILED.value,
                error_message=str(e),
            )
            return result

    # ------------------------------------------------------------------ #
    #  Composer: open, text, media — shared across modes                  #
    # ------------------------------------------------------------------ #

    async def _open_composer(self, group_url, group_name, text, result, mode):
        """Click 'Create a post' and find the dialog. Returns (state, result)."""
        state = ComposerState.GROUP_OPENED

        clicked = await self.fb.click_create_post()
        if not clicked:
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = "Could not click 'Create a post' button"
            result["composer_state"] = ComposerState.FAILED
            self._log_db_fail(group_url, group_name, result)
            return ComposerState.FAILED, result

        await asyncio.sleep(self.timing.get("form_delay", 3))

        safety = await self.fb.check_safety()
        if safety != FacebookState.OK:
            result["status"] = self._map_safety_state(safety)
            result["error"] = f"Safety issue after opening form: {safety.value}"
            result["composer_state"] = ComposerState.FAILED
            self._log_db_fail(group_url, group_name, result)
            return ComposerState.FAILED, result

        # Find the dialog
        dialog = await self._find_composer_dialog()
        if dialog is None:
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = "Post composer dialog not found after clicking create"
            result["composer_state"] = ComposerState.FAILED
            self._log_db_fail(group_url, group_name, result)
            return ComposerState.FAILED, result

        logger.info("[POST] Composer opened: SUCCESS")
        logger.info("[POST] Dialog detected: YES")

        if not await dialog.is_visible():
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = "Post composer dialog disappeared"
            result["composer_state"] = ComposerState.FAILED
            logger.error("[POST] Dialog disappeared unexpectedly. Stopping.")
            return ComposerState.FAILED, result

        # Store dialog reference on result for later use
        result["_dialog"] = dialog
        state = ComposerState.COMPOSER_OPENED
        result["composer_state"] = state
        return state, result

    async def _enter_text(self, dialog, text, result):
        """Type text into the dialog. Returns (state, result).

        Does full DOM diagnostics before searching for text field.
        Checks contenteditable, role=textbox, textarea, and other candidates.
        """
        # Retrieve dialog from result if not passed directly
        if dialog is None:
            dialog = result.get("_dialog")
        if dialog is None:
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = "No dialog reference for text entry"
            result["composer_state"] = ComposerState.FAILED
            return ComposerState.FAILED, result

        if not await dialog.is_visible():
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = "Dialog disappeared before text entry"
            result["composer_state"] = ComposerState.FAILED
            logger.error("[POST] Dialog disappeared before text entry.")
            return ComposerState.FAILED, result

        logger.info("[POST] Searching composer text input...")

        # DOM diagnostics — count all candidate types
        ce_count = 0
        tb_count = 0
        ta_count = 0
        try:
            ce_count = await dialog.locator('[contenteditable="true"]').count()
        except Exception:
            pass
        try:
            tb_count = await dialog.locator('[role="textbox"]').count()
        except Exception:
            pass
        try:
            ta_count = await dialog.locator('textarea').count()
        except Exception:
            pass

        logger.info(f"[POST] contenteditable count: {ce_count}")
        logger.info(f"[POST] role=textbox count: {tb_count}")
        logger.info(f"[POST] textarea count: {ta_count}")

        # Build list of candidates with metadata
        candidates = []

        # Candidate 1: contenteditable div with role=textbox (most likely Facebook composer)
        for sel in ['div[role="textbox"][contenteditable="true"]', '[contenteditable="true"]']:
            try:
                els = dialog.locator(sel)
                count = await els.count()
                for i in range(count):
                    el = els.nth(i)
                    try:
                        visible = await el.is_visible()
                        if not visible:
                            continue
                        tag = await el.evaluate('e => e.tagName')
                        role = await el.evaluate('e => e.getAttribute("role") || ""')
                        aria_label = await el.evaluate('e => e.getAttribute("aria-label") || ""')
                        ce_val = await el.evaluate('e => e.getAttribute("contenteditable") || ""')
                        bbox = await el.bounding_box()
                        candidates.append({
                            'selector': sel,
                            'index': i,
                            'tag': tag,
                            'role': role,
                            'aria_label': aria_label,
                            'contenteditable': ce_val,
                            'visible': True,
                            'bbox': bbox,
                            'score': 10 if role == 'textbox' else 5,
                        })
                        logger.info(f"[POST] Candidate #{len(candidates)-1}:")
                        logger.info(f"    tag: {tag}")
                        logger.info(f"    role: {role}")
                        logger.info(f"    aria-label: {aria_label}")
                        logger.info(f"    contenteditable: {ce_val}")
                        logger.info(f"    visible: YES")
                    except Exception:
                        continue
            except Exception:
                continue

        # Candidate 2: textarea
        try:
            els = dialog.locator('textarea')
            count = await els.count()
            for i in range(count):
                el = els.nth(i)
                try:
                    visible = await el.is_visible()
                    if not visible:
                        continue
                    tag = await el.evaluate('e => e.tagName')
                    aria_label = await el.evaluate('e => e.getAttribute("aria-label") || ""')
                    placeholder = await el.evaluate('e => e.getAttribute("placeholder") || ""')
                    bbox = await el.bounding_box()
                    candidates.append({
                        'selector': 'textarea',
                        'index': i,
                        'tag': tag,
                        'role': '',
                        'aria_label': aria_label,
                        'placeholder': placeholder,
                        'visible': True,
                        'bbox': bbox,
                        'score': 3,
                    })
                    logger.info(f"[POST] Candidate #{len(candidates)-1}:")
                    logger.info(f"    tag: {tag}")
                    logger.info(f"    aria-label: {aria_label}")
                    logger.info(f"    placeholder: {placeholder}")
                    logger.info(f"    visible: YES")
                except Exception:
                    continue
        except Exception:
            pass

        if not candidates:
            logger.error("[POST] Text field: NOT FOUND")
            logger.error("[POST] No visible contenteditable, textbox, or textarea in dialog")
            await self._save_composer_diagnostics("text_field_not_found")
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = "Could not find post text input field inside dialog"
            result["composer_state"] = ComposerState.FAILED
            return ComposerState.FAILED, result

        # Sort by score descending — pick the best candidate
        candidates.sort(key=lambda c: c['score'], reverse=True)
        best = candidates[0]

        logger.info(f"[POST] Text field: FOUND")
        logger.info(f"[POST] Text field tag: {best['tag']}")
        logger.info(f"[POST] Text field role: {best.get('role', '')}")
        logger.info(f"[POST] Text field contenteditable: {best.get('contenteditable', '')}")
        logger.info(f"[POST] Text field visible: YES")

        # Type text
        try:
            element = dialog.locator(best['selector']).nth(best['index'])
            await element.click()
            await asyncio.sleep(0.5)
            await self.page.keyboard.type(text, delay=10)
            logger.info("[POST] Text entered: SUCCESS")
            state = ComposerState.TEXT_ENTERED
            result["composer_state"] = state
            return state, result
        except Exception as e:
            logger.error(f"[POST] Error typing text: {e}")
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = f"Error typing text: {e}"
            result["composer_state"] = ComposerState.FAILED
            return ComposerState.FAILED, result

    async def _attach_media(self, dialog, result):
        """Attach photos and videos. Returns (state, result)."""
        if dialog is None:
            dialog = result.get("_dialog")
        if dialog is None:
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = "No dialog reference for media attachment"
            result["composer_state"] = ComposerState.FAILED
            return ComposerState.FAILED, result

        # --- Photos ---
        photos_attached = False
        if self.media.has_photos:
            logger.info(f"[POST] Photo attachment control: searching...")
            photos_attached = await self._attach_photos_in_dialog(dialog)
            if self.media.has_photos and not photos_attached:
                logger.warning("[POST] Photos: COULD NOT ATTACH (non-fatal, continuing)")
            elif photos_attached:
                logger.info(f"[POST] Photos attached: {len(self.media.photos)} — SUCCESS")
        else:
            logger.info("[POST] Photos: 0 (none to attach)")

        # --- Videos ---
        videos_attached = False
        if self.media.has_videos:
            logger.info(f"[POST] Video attachment control: searching...")
            videos_attached = await self._attach_videos_in_dialog(dialog)
            if self.media.has_videos and not videos_attached:
                logger.warning("[POST] Videos: COULD NOT ATTACH (non-fatal, continuing)")
            elif videos_attached:
                logger.info(f"[POST] Videos attached: {len(self.media.videos)} — SUCCESS")
        else:
            logger.info("[POST] Videos: 0 (none to attach)")

        logger.info("[POST] Media check: DONE")
        state = ComposerState.VIDEO_ATTACHED
        result["composer_state"] = state
        return state, result

    # ------------------------------------------------------------------ #
    #  Mode-specific finalization                                          #
    # ------------------------------------------------------------------ #

    async def _dry_run(self, group_url, group_name, text, result):
        """DRY_RUN mode — validate everything, do NOT publish."""
        logger.info("[POST] Mode: DRY_RUN")

        photo_count = len(self.media.photos) if self.media.has_photos else 0
        video_count = len(self.media.videos) if self.media.has_videos else 0
        logger.info(f"[POST] Photos: {photo_count}")
        logger.info(f"[POST] Videos: {video_count}")

        # Show text preview
        logger.info(f"[POST] Text variation #{result['text_variation_index']}:")
        text_lines = text.strip().split("\n")
        for line in text_lines[:5]:
            logger.info(f"  {line}")
        if len(text_lines) > 5:
            logger.info(f"  ... ({len(text_lines)} lines total)")

        logger.info("[POST] Ready to publish: YES (validated)")
        logger.info("[POST] Publishing: SKIPPED (DRY_RUN)")

        state = ComposerState.DRY_RUN_VALIDATED
        result["status"] = PublicationStatus.SUCCESS.value
        result["error"] = "DRY_RUN - no actual publication"
        result["composer_state"] = state

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
        """MANUAL_APPROVAL mode — wait for user confirmation before publishing."""
        logger.info("[POST] Mode: MANUAL_APPROVAL")
        logger.info(f"[POST] Text variation #{result['text_variation_index']}:")
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
                result["composer_state"] = ComposerState.FAILED
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
        """AUTO mode — publish automatically."""
        return await self._actual_publish(group_url, group_name, text, result)

    async def _actual_publish(self, group_url, group_name, text, result):
        """Click Publish and verify. All dialog-scoped."""
        dialog = result.get("_dialog")
        if dialog is None:
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = "No dialog reference for publishing"
            result["composer_state"] = ComposerState.FAILED
            return result

        # Final safety check
        safety = await self.fb.check_safety()
        if safety != FacebookState.OK:
            result["status"] = self._map_safety_state(safety)
            result["error"] = f"Safety issue before submit: {safety.value}"
            result["composer_state"] = ComposerState.FAILED
            self._log_db_fail(group_url, group_name, result)
            return result

        if not await dialog.is_visible():
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = "Dialog disappeared before publish"
            result["composer_state"] = ComposerState.FAILED
            logger.error("[POST] Dialog disappeared before publish. Stopping.")
            return result

        logger.info("[POST] Ready to publish: YES")
        posted = await self._click_post_button_in_dialog(dialog)
        if not posted:
            result["status"] = PublicationStatus.FAILED.value
            result["error"] = "Could not click 'Post' button in composer"
            result["composer_state"] = ComposerState.FAILED
            self._log_db_fail(group_url, group_name, result)
            return result

        logger.info("[POST] Publish clicked")
        result["composer_state"] = ComposerState.PUBLISH_CLICKED

        await asyncio.sleep(self.timing.get("submit_delay", 5))

        # Safety after posting
        safety = await self.fb.check_safety()
        if safety != FacebookState.OK:
            result["status"] = self._map_safety_state(safety)
            result["error"] = f"Safety issue after posting: {safety.value}"
            result["composer_state"] = ComposerState.FAILED
            self._log_db_fail(group_url, group_name, result)
            return result

        # Success
        result["status"] = PublicationStatus.SUCCESS.value
        result["error"] = None
        result["composer_state"] = ComposerState.PUBLICATION_CONFIRMED
        self._consecutive_failures = 0

        self.db.log_publication(
            group_url=group_url,
            group_name=group_name,
            text_variation_index=result["text_variation_index"],
            text_preview=text[:500],
            photos_used=self.media.photos if self.media.has_photos else [],
            video_used=self.media.has_videos,
            status=PublicationStatus.SUCCESS.value,
            post_url=result["post_url"],
        )

        logger.info("[POST] Publication confirmed: SUCCESS")
        return result

    # ------------------------------------------------------------------ #
    #  Dialog helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _find_composer_dialog(self):
        """Find the ACTUAL composer dialog by analyzing all visible [role="dialog"] elements.

        Facebook may show multiple dialogs (cookies, accessibility, etc.).
        We pick the one that actually contains composer controls.
        """
        # Wait for at least one dialog to appear (Facebook SPA may take time)
        for attempt in range(10):
            try:
                dialog_count = await self.page.locator('[role="dialog"]').count()
                if dialog_count > 0:
                    break
            except Exception:
                pass
            await asyncio.sleep(1)
        else:
            logger.error('[POST] No [role="dialog"] found after 10 seconds')
            return None

        logger.info(f"[POST] Visible dialogs: {dialog_count}")

        # Analyze each dialog to find the actual composer
        best_dialog = None
        best_score = -1

        for idx in range(dialog_count):
            try:
                dialog = self.page.locator('[role="dialog"]').nth(idx)
                is_visible = await dialog.is_visible()
                if not is_visible:
                    logger.info(f"[POST] Dialog #{idx}: NOT VISIBLE — skipping")
                    continue

                # Count composer indicators inside this dialog
                contenteditable_count = 0
                textbox_count = 0
                textarea_count = 0
                file_input_count = 0
                post_button_count = 0
                dialog_text = ""

                try:
                    contenteditable_count = await dialog.locator('[contenteditable="true"]').count()
                except Exception:
                    pass
                try:
                    textbox_count = await dialog.locator('[role="textbox"]').count()
                except Exception:
                    pass
                try:
                    textarea_count = await dialog.locator('textarea').count()
                except Exception:
                    pass
                try:
                    file_input_count = await dialog.locator('input[type="file"]').count()
                except Exception:
                    pass
                try:
                    post_button_count = await dialog.locator('div[role="button"]').count()
                except Exception:
                    pass
                try:
                    dialog_text = await dialog.inner_text()
                    dialog_text = dialog_text[:200].replace("\n", " ")
                except Exception:
                    pass

                score = contenteditable_count * 3 + textbox_count * 3 + textarea_count * 2 + file_input_count + post_button_count

                logger.info(f"[POST] Dialog #{idx}:" )
                logger.info(f"    visible: YES")
                logger.info(f"    contenteditable: {contenteditable_count}")
                logger.info(f"    role=textbox: {textbox_count}")
                logger.info(f"    textarea: {textarea_count}")
                logger.info(f"    file inputs: {file_input_count}")
                logger.info(f"    buttons: {post_button_count}")
                logger.info(f"    text: {dialog_text[:100]}")
                logger.info(f"    score: {score}")

                if score > best_score:
                    best_score = score
                    best_dialog = dialog
                    logger.info(f"    -> NEW BEST COMPOSER CANDIDATE")

            except Exception as e:
                logger.warning(f"[POST] Dialog #{idx}: error analyzing: {e}")
                continue

        if best_dialog is None:
            logger.error("[POST] No composer dialog found among visible dialogs")
            await self._save_composer_diagnostics("no_composer_found")
            return None

        if best_score == 0:
            logger.warning("[POST] Best dialog has score 0 — may not be the composer")

        logger.info(f"[POST] Actual composer: FOUND (score={best_score})")
        return best_dialog

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
                    logger.info("[POST] Photos attached (page-level fallback)")
                    return True
            except Exception:
                pass

            return False
        except Exception as e:
            logger.error(f"[POST] Error attaching photos: {e}")
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
                    logger.info("[POST] Videos attached (page-level fallback)")
                    return True
            except Exception:
                pass

            return False
        except Exception as e:
            logger.error(f"[POST] Error attaching videos: {e}")
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
                    for idx in range(count):
                        element = elements.nth(idx)
                        if await element.is_visible():
                            disabled = await element.get_attribute("aria-disabled")
                            if disabled == "true":
                                logger.warning("[POST] Post button is disabled")
                                return False
                            await element.click()
                            return True
            except Exception:
                continue

        # Fallback: page-level search
        try:
            page_buttons = self.page.locator('[aria-label="\u041e\u043f\u0443\u0431\u043b\u0456\u043a\u0443\u0432\u0430\u0442\u0438"]')
            count = await page_buttons.count()
            if count > 0:
                element = page_buttons.first
                if await element.is_visible():
                    await element.click()
                    logger.info("[POST] Publish clicked (page-level fallback)")
                    return True
        except Exception:
            pass

        logger.warning("[POST] Could not find Post button in dialog")
        return False

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    async def _save_composer_diagnostics(self, label: str):
        """Save screenshot and page info when composer detection fails."""
        try:
            Path("logs").mkdir(exist_ok=True)
            path = f"logs/composer_{label}.png"
            await self.page.screenshot(path=path)
            logger.info(f"[POST] Screenshot saved: {path}")
        except Exception as e:
            logger.warning(f"[POST] Could not save screenshot: {e}")

        try:
            page_url = self.page.url
            title = await self.page.title()
            dialog_count = await self.page.locator('[role="dialog"]').count()
            logger.info(f"[POST] Diagnostic info:")
            logger.info(f"    URL: {page_url}")
            logger.info(f"    Title: {title}")
            logger.info(f"    Dialog count: {dialog_count}")
        except Exception:
            pass

    def _log_db_fail(self, group_url, group_name, result):
        """Log a failed publication to the database."""
        self.db.log_publication(
            group_url=group_url,
            group_name=group_name,
            text_variation_index=result.get("text_variation_index"),
            status=result.get("status", PublicationStatus.FAILED.value),
            error_message=result.get("error"),
        )

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
