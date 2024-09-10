from datetime import datetime
from typing import Any, TypedDict

from playwright.async_api import Page as PageAsync


class ViewPortSize(TypedDict):
    width: int
    height: int
    content_height: int


class PlaywrightAsync:
    STRIP_RETURN = "return window."

    def __init__(self, page: PageAsync):
        self._page = page

    async def run_js(self, js: str) -> Any:
        if js.startswith(self.STRIP_RETURN):
            js = js[len(self.STRIP_RETURN):]

        print(type(self._page))

        return await self._page.evaluate(js)

    async def take_screenshot(self) -> bytes:
        return await self._page.screenshot(path=f"debug-ss/{datetime.now()}.png", type="png", full_page=True,
                                           omit_background=True)

    async def set_viewport_size(self, width: int, height: int) -> None:
        await self._page.set_viewport_size({"width": width, "height": height})

    async def get_viewport_size(self) -> ViewPortSize:
        width, height, scroll_height = await self.run_js(
            "[window.innerWidth, window.innerHeight, document.documentElement.scrollHeight]"
        )

        return {"width": width, "height": height, "content_height": scroll_height}
