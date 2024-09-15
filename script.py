import asyncio
from arachne.agent import WebWeaver


async def _main():
    with open(".env", "r") as f:
        # OpenAI API Key
        api_key = f.read()

    ww = WebWeaver(api_key)

    await ww.setup_web()
    await ww._main()


asyncio.run(_main())
