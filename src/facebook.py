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

    async def navigate_to(self, url: str, wait_until: str = "domcontentloaded") -> Tuple[bool, str]:
        """
        Navigate to a URL and perform safety checks.
        Returns (success, current_url).
        """
        try:
            logger.info(f"Navigating to: {url}")
            await self.page.goto(url, wait_until=wait_until, timeout=30000)
            await asyncio.sleep(3)

            current_url = self.page.url
            logger.info(f"Current URL: {current_url}")

            # Verify we actually navigated to the target
            if current_url == "about:blank":
                logger.error("Navigation failed - browser is still on about:blank")
                return False, current_url

            # Perform safety check after navigation
            state = await self.check_safety()
            if state != FacebookState.OK:
                logger.warning(f"Safety issue detected: {state.value}")
                return False, current_url

            return True, current_url
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            current_url = self.page.url if self.page else "unknown"
            return False, current_url

    async def check_safety(self) -> FacebookState:
        """Check the current page for Facebook safety prompts."""
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
        post_selectors = [
            '[aria-label="Create a post"]',
            '[aria-label="\u0421\u0442\u0432\u043e\u0440\u0438\u0442\u0438 \u0434\u043e\u043f\u0438\u0441"]',
            '[aria-label="Write something..."]',
            '[aria-label="\u041d\u0430\u043f\u0438\u0448\u0456\u0442\u044c \u0449\u043e\u0441\u044c..."]',
            '[data-pagelet="FeedComposer"]',
            'div[role="button"]:has-text("\u041d\u0430\u043f\u0438\u0448\u0456\u0442\u044c \u0449\u043e\u0441\u044c")',
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
            '[aria-label="\u0421\u0442\u0432\u043e\u0440\u0438\u0442\u0438 \u0434\u043e\u043f\u0438\u0441"]',
            '[aria-label="Write something..."]',
            '[aria-label="\u041d\u0430\u043f\u0438\u0448\u0456\u0442\u044c \u0449\u043e\u0441\u044c..."]',
            'div[role="button"]:has-text("\u041d\u0430\u043f\u0438\u0448\u0456\u0442\u044c \u0449\u043e\u0441\u044c")',
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
        """Check for common Facebook errors on the page."""
        error_selectors = [
            ("div[role='alert']", "Facebook alert detected"),
            ("div[class*='error']", "Facebook error page"),
            ("div:has-text('Something went wrong')", "Something went wrong"),
            ("div:has-text('\u0429\u043e\u0441\u044c \u043f\u0456\u0434\u043b\u043e \u043d\u0435 \u0442\u0430\u043a')", "Something went wrong (UA)"),
            ("div:has-text(\"This content isn't available\")", "Content not available"),
            ("div:has-text('\u0426\u0435\u0439 \u043a\u043e\u043d\u0442\u0435\u043d\u0442 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0438\u0439')", "Content not available (UA)"),
        ]

        for selector, message in error_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    text = await element.text_content() or message
                    logger.warning(f"Facebook error detected: {message} -- {text[:200]}")
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
