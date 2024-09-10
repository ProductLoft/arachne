from asyncio import Protocol
from pathlib import Path
from typing import Dict, Tuple

from arachne._utils import load_js
from arachne.browser import PlaywrightAsync

from playwright.async_api import Page as PageAsync

TagToXPath = Dict[int, str]


class IWebWeaver(Protocol):
    async def page_to_image(self, driver: PageAsync) -> Tuple[bytes, Dict[int, str]]:
        raise NotImplementedError()

    async def page_to_text(self, driver: PageAsync) -> Tuple[str, Dict[int, str]]:
        raise NotImplementedError()


class WebWeaver(IWebWeaver):
    _JS_TAG_UTILS = Path(__file__).parent / "tags.min.js"

    def __init__(self):
        self._js_utils: str = load_js(self._JS_TAG_UTILS)

    async def page_to_image(
        self,
        driver: PageAsync,
        tag_text_elements: bool = False,
        tagless: bool = False,
        keep_tags_showing: bool = False,
    ) -> Tuple[bytes, TagToXPath]:
        tag_to_xpath = (
            await self._tag_page(driver, tag_text_elements) if not tagless else {}
        )
        screenshot = await self._take_screenshot(PlaywrightAsync(driver))
        if not tagless and not keep_tags_showing:
            await self._remove_tags(PlaywrightAsync(driver))
        return screenshot, tag_to_xpath if not tagless else {}

    async def page_to_text(
        self,
        driver: PageAsync,
        tag_text_elements: bool = False,
        tagless: bool = False,
        keep_tags_showing: bool = False,
    ) -> Tuple[str, TagToXPath]:
        image, tag_to_xpath = await self.page_to_image(
            driver, tag_text_elements, tagless, keep_tags_showing
        )
        page_text = self._run_ocr(image)
        return page_text, tag_to_xpath

    async def page_to_image_and_text(
        self,
        driver: PageAsync,
        tag_text_elements: bool = False,
        tagless: bool = False,
        keep_tags_showing: bool = False,
    ) -> Tuple[bytes, str, TagToXPath]:
        image, tag_to_xpath = await self.page_to_image(
            driver, tag_text_elements, tagless, keep_tags_showing
        )
        return image, "", tag_to_xpath

    @staticmethod
    async def _take_screenshot(browser: PlaywrightAsync) -> bytes:
        viewport = await browser.get_viewport_size()
        default_width = viewport["width"]

        await browser.set_viewport_size(default_width, viewport["content_height"])
        screenshot = await browser.take_screenshot()
        await browser.set_viewport_size(default_width, viewport["height"])

        return screenshot

    def _run_ocr(self, image: bytes) -> str:
        return ""

    async def _tag_page(
        self, page: PageAsync, tag_text_elements: bool = False
    ) -> Dict[int, str]:
        browser = PlaywrightAsync(page)
        await browser.run_js(self._js_utils)

        script = f"return window.tagifyWebpage({str(tag_text_elements).lower()});"
        tag_to_xpath = await browser.run_js(script)

        return {int(key): value for key, value in tag_to_xpath.items()}

    async def _remove_tags(self, browser: PlaywrightAsync) -> None:
        await browser.run_js(js=self._js_utils)
        script = "return window.removeTags();"

        await browser.run_js(script)

    async def remove_tags(self, browser: PlaywrightAsync) -> None:

        await self._remove_tags(browser)
