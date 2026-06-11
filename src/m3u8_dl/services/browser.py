from contextlib import asynccontextmanager
from typing import AsyncGenerator

from playwright.async_api import Browser, Page

# Try JWriter20 fork → official camoufox → cloverlabs fork, in that order.
# All three expose the same async_api module.
try:
    from camoufox.async_api import AsyncCamoufox
except ImportError:
    raise ImportError(
        "camoufox is not installed.\n"
        "Install one of:\n"
        "  pip install git+https://github.com/JWriter20/camoufox.git   # JWriter20 fork\n"
        "  pip install 'camoufox[geoip]'                               # official\n"
        "  pip install cloverlabs-camoufox                             # CloverLabs fork\n"
        "Then run: camoufox fetch"
    )


class BrowserService:
    def __init__(self, headless: bool = False) -> None:
        self._headless = headless
        self._browser: Browser | None = None

    @asynccontextmanager
    async def launch(self) -> AsyncGenerator["BrowserService", None]:
        # geoip spoofing improves Cloudflare bypass but requires the geoip extra.
        # Fall back silently if it isn't installed.
        try:
            browser_cm = AsyncCamoufox(headless=self._headless, geoip=True)
            async with browser_cm as browser:
                self._browser = browser
                try:
                    yield self
                finally:
                    self._browser = None
        except Exception as exc:
            if "geoip" not in str(exc).lower():
                raise
            from rich.console import Console
            Console().print(
                "[yellow]geoip extra not installed — launching without geo spoofing.[/yellow]\n"
                "For better Cloudflare bypass, run: pip install 'camoufox[geoip]'"
            )
            async with AsyncCamoufox(headless=self._headless) as browser:
                self._browser = browser
                try:
                    yield self
                finally:
                    self._browser = None

    async def new_page(self) -> Page:
        if self._browser is None:
            raise RuntimeError("Browser not running. Use `async with browser_service.launch()`.")
        return await self._browser.new_page()

    async def get_cookies(self, page: Page) -> dict[str, str]:
        cookies = await page.context.cookies()
        return {c["name"]: c["value"] for c in cookies}

    async def get_user_agent(self, page: Page) -> str:
        return await page.evaluate("navigator.userAgent")
