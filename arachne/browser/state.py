import asyncio
import tempfile
import uuid
from asyncio import Protocol
from contextvars import ContextVar
from dataclasses import field, dataclass
from datetime import datetime
import time
from enum import StrEnum

from playwright.async_api import BrowserContext, Error, Page, Playwright, async_playwright
from pydantic import BaseModel
from typing import Any, Awaitable, Callable, Protocol
import structlog

from arachne.exceptions import UnknownBrowserType, UnknownErrorWhileCreatingBrowserContext, MissingBrowserStatePage, \
    FailedToNavigateToUrl, FailedToStopLoadingPage, FailedToReloadPage

log = structlog.get_logger()

BrowserCleanupFunc = Callable[[], None] | None


@dataclass
class SkyvernContext:
    request_id: str | None = None
    organization_id: str | None = None
    task_id: str | None = None
    workflow_id: str | None = None
    workflow_run_id: str | None = None
    max_steps_override: int | None = None
    totp_codes: dict[str, str | None] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"SkyvernContext(request_id={self.request_id}, organization_id={self.organization_id}, task_id={self.task_id}, workflow_id={self.workflow_id}, workflow_run_id={self.workflow_run_id}, max_steps_override={self.max_steps_override})"

    def __str__(self) -> str:
        return self.__repr__()


_context: ContextVar[SkyvernContext | None] = ContextVar(
    "Global context",
    default=None,
)


def current() -> SkyvernContext | None:
    """
    Get the current context

    Returns:
        The current context, or None if there is none
    """
    return _context.get()


class VideoArtifact(BaseModel):
    video_path: str | None = None
    video_artifact_id: str | None = None
    video_data: bytes = bytes()


class BrowserArtifacts(BaseModel):
    video_artifacts: list[VideoArtifact] = []
    har_path: str | None = None
    traces_dir: str | None = None

class BrowserContextCreator(Protocol):
    def __call__(
            self, playwright: Playwright, **kwargs: dict[str, Any]
    ) -> Awaitable[tuple[BrowserContext, BrowserArtifacts, BrowserCleanupFunc]]: ...


class BrowserContextFactory:

    _creators: dict[str, BrowserContextCreator] = {}
    _validator: Callable[[Page], Awaitable[bool]] | None = None

    @staticmethod
    def get_subdir() -> str:
        curr_context = current()
        if curr_context and curr_context.task_id:
            return curr_context.task_id
        elif curr_context and curr_context.request_id:
            return curr_context.request_id
        return str(uuid.uuid4())

    @staticmethod
    def build_browser_args() -> dict[str, Any]:
        video_dir = f"video/{datetime.utcnow().strftime('%Y-%m-%d')}"
        har_dir = f"video/{datetime.utcnow().strftime('%Y-%m-%d')}/{BrowserContextFactory.get_subdir()}.har"
        return {
            "user_data_dir": tempfile.mkdtemp(prefix="skyvern_browser_"),
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "color_scheme": "no-preference",
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disk-cache-size=1",
                "--start-maximized",
            ],
            "ignore_default_args": [
                "--enable-automation",
            ],
            "record_har_path": har_dir,
            "record_video_dir": video_dir,
            "viewport": {
                "width": 1920,
                "height": 1080,
            },
        }

    @staticmethod
    def build_browser_artifacts(
            video_artifacts: list[VideoArtifact] | None = None,
            har_path: str | None = None,
            traces_dir: str | None = None,
    ) -> BrowserArtifacts:
        return BrowserArtifacts(
            video_artifacts=video_artifacts or [],
            har_path=har_path,
            traces_dir=traces_dir,
        )

    @classmethod
    def register_type(cls, browser_type: str, creator: BrowserContextCreator) -> None:
        cls._creators[browser_type] = creator

    @classmethod
    async def create_browser_context(
            cls, playwright: Playwright, url: str | None = None, **kwargs: dict
    ) -> tuple[BrowserContext, BrowserArtifacts, BrowserCleanupFunc]:
        browser_type = "chromium-headful"
        try:
            creator = cls._creators.get(browser_type)
            if not creator:
                raise UnknownBrowserType(browser_type)
            browser_context, browser_artifacts, cleanup_func = await creator(playwright, **kwargs)

            if url:
                await browser_context.pages[-1].goto(url)

            return browser_context, browser_artifacts, cleanup_func
        except UnknownBrowserType as e:
            raise e
        except Exception as e:
            raise UnknownErrorWhileCreatingBrowserContext(browser_type, e) from e

    @classmethod
    def set_validate_browser_context(cls, validator: Callable[[Page], Awaitable[bool]]) -> None:
        cls._validator = validator

    @classmethod
    async def validate_browser_context(cls, page: Page) -> bool:
        if cls._validator is None:
            return True
        return await cls._validator(page)




async def _create_headless_chromium(
    playwright: Playwright, **kwargs: dict
) -> tuple[BrowserContext, BrowserArtifacts, BrowserCleanupFunc]:
    browser_args = BrowserContextFactory.build_browser_args()
    browser_artifacts = BrowserContextFactory.build_browser_artifacts(har_path=browser_args["record_har_path"])
    browser_context = await playwright.chromium.launch_persistent_context(**browser_args)
    return browser_context, browser_artifacts, None


async def _create_headful_chromium(
    playwright: Playwright, **kwargs: dict
) -> tuple[BrowserContext, BrowserArtifacts, BrowserCleanupFunc]:
    browser_args = BrowserContextFactory.build_browser_args()
    browser_args.update(
        {
            "headless": False,
        }
    )
    browser_artifacts = BrowserContextFactory.build_browser_artifacts(har_path=browser_args["record_har_path"])
    browser_context = await playwright.chromium.launch_persistent_context(**browser_args)
    return browser_context, browser_artifacts, None


BrowserContextFactory.register_type("chromium-headless", _create_headless_chromium)
BrowserContextFactory.register_type("chromium-headful", _create_headful_chromium)


class BrowserState:
    instance = None

    def __init__(
            self,
            pw: Playwright | None = None,
            browser_context: BrowserContext | None = None,
            page: Page | None = None,
            browser_artifacts: BrowserArtifacts = BrowserArtifacts(),
            browser_cleanup: BrowserCleanupFunc = None,
    ):
        self.__page = page
        self.pw = pw
        self.browser_context = browser_context
        self.browser_artifacts = browser_artifacts
        self.browser_cleanup = browser_cleanup

    # Method to use when printing the object
    def __repr__(self) -> str:
        return f"BrowserState(page={self.__page}, browser_context={self.browser_context}, browser_artifacts={self.browser_artifacts}, browser_cleanup={self.browser_cleanup})"

    async def goto_page(self, url: str) -> Page:
        # TODO: Suriya this needs to go if we're going to be opening a new link in the same page
        page = await self.get_or_create_page(url)
        return page

    async def __assert_page(self) -> Page:
        page = await self.get_working_page()
        if page is not None:
            return page
        log.error("BrowserState has no page")
        raise MissingBrowserStatePage()

    async def _close_all_other_pages(self) -> None:
        cur_page = await self.get_working_page()
        if not self.browser_context or not cur_page:
            return
        pages = self.browser_context.pages
        for page in pages:
            if page != cur_page:
                await page.close()

    async def check_and_fix_state(
            self,
            url: str | None = None,
    ) -> None:
        if self.pw is None:
            log.info("Starting playwright")
            self.pw = await async_playwright().start()
            log.info("playwright is started")
        if self.browser_context is None:
            log.info("creating browser context")
            (
                browser_context,
                browser_artifacts,
                browser_cleanup,
            ) = await BrowserContextFactory.create_browser_context(
                self.pw,
                url=url,
            )
            self.browser_context = browser_context
            self.browser_artifacts = browser_artifacts
            self.browser_cleanup = browser_cleanup
            log.info("browser context is created")

        assert self.browser_context is not None

        if await self.get_working_page() is None:
            success = False
            retries = 0

            while not success and retries < 3:
                try:
                    log.info("Creating a new page")
                    page = await self.browser_context.new_page()
                    await self.set_working_page(page, 0)
                    await self._close_all_other_pages()
                    log.info("A new page is created")
                    if url:
                        log.info(f"Navigating page to {url} and waiting for 5 seconds")
                        try:
                            start_time = time.time()
                            await page.goto(url, timeout=120000)
                            end_time = time.time()
                            log.info(
                                "Page loading time",
                                loading_time=end_time - start_time,
                                url=url,
                            )
                            await asyncio.sleep(5)
                        except Error as playright_error:
                            log.warning(
                                f"Error while navigating to url: {str(playright_error)}",
                                exc_info=True,
                            )
                            raise FailedToNavigateToUrl(url=url, error_message=str(playright_error))
                        success = True
                        log.info(f"Successfully went to {url}")
                    else:
                        success = True
                except Exception as e:
                    log.exception(
                        f"Error while creating or navigating to a new page. Waiting for 5 seconds. Error: {str(e)}",
                    )
                    retries += 1
                    # Wait for 5 seconds before retrying
                    await asyncio.sleep(5)
                    if retries >= 3:
                        log.exception(f"Failed to create a new page after 3 retries: {str(e)}")
                        raise e
                    log.info(f"Retrying to create a new page. Retry count: {retries}")

    async def get_working_page(self) -> Page | None:
        if self.__page is None or self.browser_context is None or len(self.browser_context.pages) == 0:
            return None

        last_page = self.browser_context.pages[-1]
        if self.__page == last_page:
            return self.__page
        await self.set_working_page(last_page, len(self.browser_context.pages) - 1)
        return last_page

    async def set_working_page(self, page: Page | None, index: int = 0) -> None:
        self.__page = page
        if page is None:
            return
        if len(self.browser_artifacts.video_artifacts) > index:
            if self.browser_artifacts.video_artifacts[index].video_path is None:
                self.browser_artifacts.video_artifacts[index].video_path = await page.video.path()
            return

        target_lenght = index + 1
        self.browser_artifacts.video_artifacts.extend(
            [VideoArtifact()] * (target_lenght - len(self.browser_artifacts.video_artifacts))
        )
        self.browser_artifacts.video_artifacts[index].video_path = await page.video.path()
        return

    async def get_or_create_page(
            self,
            url: str | None = None,
    ) -> Page:
        log.info(f"Getting or creating page {url}")
        page = await self.get_working_page()
        if page is not None:
            return page

        try:
            await self.check_and_fix_state(
            )
        except Exception as e:
            error_message = str(e)
            if "net::ERR" not in error_message:
                raise e
            await self.close_current_open_page()
            await self.check_and_fix_state(
                url=url
            )
        await self.__assert_page()

        if not await BrowserContextFactory.validate_browser_context(await self.get_working_page()):
            await self.close_current_open_page()
            await self.check_and_fix_state(
                url=url
            )
            await self.__assert_page()

        return page

    async def close_current_open_page(self) -> None:
        await self._close_all_other_pages()
        if self.browser_context is not None:
            await self.browser_context.close()
        self.browser_context = None
        await self.set_working_page(None)

    async def stop_page_loading(self) -> None:
        page = await self.__assert_page()
        try:
            await page.evaluate("window.stop()")
        except Exception as e:
            log.exception(f"Error while stop loading the page: {repr(e)}")
            raise FailedToStopLoadingPage(url=page.url, error_message=repr(e))

    async def reload_page(self) -> None:
        page = await self.__assert_page()

        log.info(f"Reload page {page.url} and waiting for 5 seconds")
        try:
            start_time = time.time()
            await page.reload(timeout=120000)
            end_time = time.time()
            log.info(
                "Page loading time",
                loading_time=end_time - start_time,
            )
            await asyncio.sleep(5)
        except Exception as e:
            log.exception(f"Error while reload url: {repr(e)}")
            raise FailedToReloadPage(url=page.url, error_message=repr(e))

    async def close(self, close_browser_on_completion: bool = True) -> None:
        log.info("Closing browser state")
        if self.browser_context and close_browser_on_completion:
            log.info("Closing browser context and its pages")
            await self.browser_context.close()
            log.info("Main browser context and all its pages are closed")
            if self.browser_cleanup is not None:
                self.browser_cleanup()
                log.info("Main browser cleanup is excuted")
        if self.pw and close_browser_on_completion:
            log.info("Stopping playwright")
            await self.pw.stop()
            log.info("Playwright is stopped")

    async def take_screenshot(self, full_page: bool = False, file_path: str | None = None) -> bytes:
        page = await self.__assert_page()
        log.error("Taking screenshot failure")
        return None
