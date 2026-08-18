"""
Facebook interaction helpers.
Navigation, page detection, safety checks, and common Facebook interactions.
"""

import asyncio
from enum import Enum
from typing import Optional, Tuple

from loguru import logger
from playwright.async_api import Page


class FacebookState(Enum):
    """Possible Facebook page states."""
    OK = "ok"
    CAPTCHA = "captcha"
    CHECKPOINT = "checkpoint"
    RESTRICTION = "restriction"
    LOGIN_REQUIRED = "login_required"
    UNKNOWN = "unknown"


class FacebookHelper:
    """Helper class for Facebook interactions with safety checks."""

    # Selectors for detecting Facebook safety prompts
    SAFETY_SELECTORS = {
        "captcha": [
            'iframe[src*="captcha"]',
            '[aria-label="reCAPTCHA"]',
            'div[class*="captcha"]',
            '#captcha',
        ],
        "checkpoint": [
            '[data-testid="checkpoint_title"]',
            'div[class*="checkpoint"]',
            'div[class*="security_check"]',
            '#checkpointSubmitButton',
        ],
        "restriction": [
            'div[role="alert"]',
            'div[class*="restriction"]',
            'div[class*="blocked"]',
        ],
        "login_form": [
            'button[data-testid="royal_login_button"]',
            '#login_form',
            'form[action*="login"]',
        ],
    }

    def __init__(self, page: Page):
        self.page = page

    async def navigate_to(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        """Navigate to a URL and perform safety checks."""
        try:
            await self.page.goto(url, wait_until=wait_until, timeout=30000)
            await asyncio.sleep(2)

            # Perform safety check after navigation
            state = await self.check_safety()
            if state != FacebookState.OK:
                logger.warning(f"Safety issue detected after navigating to {url}: {state.value}")
                return False

            return True
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            return False

    async def check_safety(self) -> FacebookState:
        """
        Check the current page for Facebook safety prompts.
        Returns the detected state.
        """
        for state_name, selectors in self.SAFETY_SELECTORS.items():
            for selector in selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        state_map = {
                            "captcha": FacebookState.CAPTCHA,
                            "checkpoint": FacebookState.CHECKPOINT,
                            "restriction": FacebookState.RESTRICTION,
                            "login_form": FacebookState.LOGIN_REQUIRED,
                        }
                        state = state_map.get(state_name, FacebookState.UNKNOWN)
                        logger.warning(f"Safety check detected: {state_name} ({selector})")
                        return state
                except Exception:
                    continue

        return FacebookState.OK

    async def is_facebook_group(self, url: str) -> bool:
        """Check if the given URL is a Facebook group."""
        return "facebook.com/groups/" in url.lower()

    async def get_group_name(self) -> Optional[str]:
        """Try to extract the group name from the current page."""
        selectors = [
            "h1 strong span",
            "h1 span",
            '[data-testid="group-header-title"] h1',
            "h1",
        ]
        for selector in selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    text = await element.text_content()
                    if text and text.strip():
                        return text.strip()
            except Exception:
                continue
        return None

    async def can_create_post(self) -> bool:
        """Check if the user can create a post in the current group."""
        # Look for "Write something..." / "Напишіть щось..." post creation box
        post_selectors = [
            '[aria-label="Create a post"]',
            '[aria-label="Створити допис"]',
            '[aria-label="Write something..."]',
            '[aria-label="Напишіть щось..."]',
            '[data-pagelet="FeedComposer"]',
            'div[role="button"]:has-text("Напишіть щось")',
            'div[role="button"]:has-text("Write something")',
        ]

        for selector in post_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    return True
            except Exception:
                continue

        return False

    async def click_create_post(self) -> bool:
        """Click the 'Create a post' button in the group."""
        post_selectors = [
            '[aria-label="Create a post"]',
            '[aria-label="Створити допис"]',
            '[aria-label="Write something..."]',
            '[aria-label="Напишіть щось..."]',
            'div[role="button"]:has-text("Напишіть щось")',
            'div[role="button"]:has-text("Write something")',
        ]

        for selector in post_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    await element.click()
                    await asyncio.sleep(2)
                    return True
            except Exception:
                continue

        logger.warning("Could not find 'Create a post' button")
        return False

    async def get_page_title(self) -> str:
        """Get the current page title."""
        try:
            return await self.page.title()
        except Exception:
            return ""

    async def check_for_errors(self) -> Tuple[bool, str]:
        """
        Check for common Facebook errors on the page.
        Returns (has_error, error_message).
        """
        error_selectors = [
            ("div[role='alert']", "Facebook alert detected"),
            ("div[class*='error']", "Facebook error page"),
            ("div:has-text('Something went wrong')", "Something went wrong"),
            ("div:has-text('Щось пішло не так')", "Something went wrong (UA)"),
            ("div:has-text('This content isn't available')", "Content not available"),
            ("div:has-text('Цей контент недоступний')", "Content not available (UA)"),
        ]

        for selector, message in error_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    text = await element.text_content() or message
                    logger.warning(f"Facebook error detected: {message} — {text[:200]}")
                    return True, text[:500]
            except Exception:
                continue

        return False, ""

    async def safe_scroll(self, pixels: int = 300):
        """Scroll the page by a number of pixels."""
        try:
            await self.page.mouse.wheel(0, pixels)
            await asyncio.sleep(1)
        except Exception as e:
            logger.debug(f"Scroll error (non-critical): {e}")

    async def take_screenshot(self, path: str = "logs/debug_screenshot.png"):
        """Take a screenshot for debugging."""
        try:
            await self.page.screenshot(path=path, full_page=False)
            logger.info(f"Screenshot saved to {path}")
        except Exception as e:
            logger.debug(f"Screenshot failed: {e}")
