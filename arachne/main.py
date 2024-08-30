import asyncio

from browser.manager import BrowserManager, BrowserState, MissingBrowserState, createBrowserManager


async def main():
    print("Main function started")
    bm = await createBrowserManager("https://www.google.com")
    print("Browser state created")
    # await bm.open_url("https://suriya.cc")


if __name__ == "__main__":

    asyncio.run(main())


