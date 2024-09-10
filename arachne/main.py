import asyncio
from asyncio import sleep

from browser.manager import BrowserManager, BrowserState, MissingBrowserState, createBrowserManager
import structlog

log = structlog.get_logger()


async def main():
    log.info("Main function started")
    bm = await createBrowserManager("https://www.google.com")
    await bm.state.goto_page("https://www.suriya.cc")
    await sleep(5)
    log.info("Browser state created")


if __name__ == "__main__":
    asyncio.run(main())
