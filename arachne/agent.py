from asyncio import Protocol
from pathlib import Path
from typing import Dict, Tuple
import io

from regex import regex
import json

import base64
from PIL import Image
import requests

from icecream import ic

from arachne._utils import load_js
from arachne.browser import PlaywrightAsync
from playwright.async_api import async_playwright

from playwright.async_api import Page as PageAsync

TagToXPath = Dict[int, str]


class IWebWeaver(Protocol):
    async def page_to_image(self, driver: PageAsync) -> Tuple[bytes, Dict[int, str]]:
        raise NotImplementedError()

    async def page_to_text(self, driver: PageAsync) -> Tuple[str, Dict[int, str]]:
        raise NotImplementedError()


class WebWeaver(IWebWeaver):
    _JS_TAG_UTILS = Path(__file__).parent / "tags.min.js"

    def __init__(self, api_key: str):
        self._js_utils: str = load_js(self._JS_TAG_UTILS)
        self.tag_to_xpath: TagToXPath = {}
        self.api_key = api_key

    async def setup_web(self):
        p = await async_playwright().__aenter__()
        self.browser = await p.chromium.launch(headless=False)
        self.page = await self.browser.new_page()

    async def page_to_image(
            self,
            driver: PageAsync,
            tag_text_elements: bool = False,
            tagless: bool = False,
            keep_tags_showing: bool = False,
    ) -> Tuple[bytes, TagToXPath]:
        self.tag_to_xpath = (
            await self._tag_page(driver, tag_text_elements) if not tagless else {}
        )
        screenshot = await self._take_screenshot(PlaywrightAsync(driver))
        if not tagless and not keep_tags_showing:
            await self._remove_tags(PlaywrightAsync(driver))
        return screenshot, self.tag_to_xpath if not tagless else {}

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
        # await browser.set_viewport_size(default_width, viewport["height"])

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

        self.page = None

    # Function to encode the image
    def encode_image(self, input_image: Image, height=2048):

        # Get the width and height of the image
        width, img_height = input_image.size

        # Calculate the number of segments
        num_segments = (img_height + height - 1) // height
        image_resp = []

        # Split the image into segments
        for i in range(num_segments if num_segments < 10 else 10):
            # Calculate the box for cropping
            top = i * height
            bottom = min((i + 1) * height, img_height)
            box = (0, top, width, bottom)

            # Crop the image
            segment = input_image.crop(box)
            buffered = io.BytesIO()
            segment.save(buffered, format="PNG")
            image_resp.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"
                }})

        return image_resp

    # Path to your image
    # image_path = "../test-images/screenshot_20240909_173326.png"

    # Define tools/actions

    async def read_page(self):
        """
        Use to read the current state of the page
        """
        image, inner_tag_to_xpath = await self.page_to_image(self.page)
        ic(type(inner_tag_to_xpath))
        ic(type(image))
        self.tag_to_xpath.clear()
        self.tag_to_xpath.update(inner_tag_to_xpath)
        image_buffer = io.BytesIO(image)
        return self.encode_image(Image.open(image_buffer))

    async def go_to_page(self, url: str) -> [Image]:
        await self.page.goto(url)
        return await self.read_page()


    async def click(self, element_id: int) -> str:
        """
        Click on an element based on element_id and return the new page state
        """
        # ic(element_id)
        # ic(type(element_id))
        x_path = self.tag_to_xpath[element_id]
        ic(x_path)
        element = self.page.locator(x_path)
        await element.scroll_into_view_if_needed()
        await self.page.wait_for_timeout(1000)
        await element.click()
        await self.page.wait_for_timeout(2000)
        return await self.read_page_impl()

    async def type_text(self, text: str, element_id: int ) -> str:
        """
        Input text into a textbox based on element_id and return the new page state
        """
        x_path = self.tag_to_xpath[element_id]
        await self.page.locator(x_path).press_sequentially(text)
        return await self.read_page_impl()

    async def press_key(self, key: str) -> str:
        """
        Press a key on the keyboard and return the new page state
        """
        await self.page.keyboard.press(key)
        await self.page.wait_for_timeout(2000)
        return await self.read_page_impl()

    async def _main(self):

        # with open("config.json", "r") as f:
        #     google_cloud_credentials = json.load(f)

        tasks_history = []

        question = '''
    biography:
    name: Sammy Ganesh
    Email: sayyampe@andrew.cmu.edu
    Phone: +14122872364
    
    fill these details in the web page    
        '''

        site_name = "https://job-boards.greenhouse.io/point72/jobs/7441962002?jobCode=IVS-0012382&location=null"

        await self.page.goto(site_name)

        ic(type(self.page))

        screenshot, tag_to_xpath = await self.page_to_image(self.page)

        screenshot_buffer = io.BytesIO(screenshot)
        images = self.encode_image(Image.open(screenshot_buffer))
        notDone = True

        while notDone:

            ic("len(images)", len(images))

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            template = f"""
        You are a web interaction agent. Use the read page tool to understand where you currently are. The current page and its contents are provided you are starting with the site {site_name}
        input elements are tagged in red with an id integer
        @ is used to tag clickable elements
        # is used to tag text input elements
        $ is used to tag text elements
    
    
        You have access to the following tools:
        only provide a valid tag_id present in the image in red
        go_to_url: Use to go to a new url. Takes in "url"
        read_page: Use to read the current state of the page
        click: Click on an element based on element_id and return the new page state takes in "tag_id"
        type_text: Input text into a textbox based on element_id and return the new page state. Takes in list of ["input_text", tag_id:int]
    
    
        Use the following json format:
    
        {{
        "question": "the input question you must answer"
        "thought": "you should always think about what to do"
        "action": "the action to take, should be one of [read_page, click, type_text]"
        "action_input": "the input to the action"
        }}
        ... (this Thought/Action/Action_Input/Observation can repeat N times)
    
        if you've reached the end of the task, you can provide the final answer in the following format:
        {{ "Thought": I now know the final answer
        "final_answer": the final answer to the original input question
        }}
    
        These were previous tasks you completed:
    
        {tasks_history}
    
        Begin!
    
        Question: {question}
        """

            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": template
                            },
                        ]
                    }
                ],
                "max_tokens": 10000,
            }
            # resp[0]
            #
            ic(payload)
            payload["messages"][0]["content"].extend(images)
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            try:
                resp = response.json()["choices"][0]["message"]["content"]
                pattern = regex.compile(r'\{(?:[^{}]|(?R))*\}')
                resp_content = pattern.findall(resp)
                resp_json = json.loads(resp_content[0])
                ic(resp_json)

                if "final_answer" in resp:
                    notDone = False
                else:
                    tasks_history.append(resp_json)

                if resp_json["action"] == "read_page":
                    ic("Reading Page")
                    await self.read_page()
                elif resp_json["action"] == "click":
                    ic("Clicking")
                    action_inputs = resp_json.get("action_input", 0)
                    await self.click(int(action_inputs))
                elif resp_json["action"] == "type_text":
                    ic("Typing")
                    if isinstance(resp_json["action_input"][0], list):
                        for action_input in resp_json["action_input"]:
                            ic(action_input)
                            await self.type_text(action_input[0], action_input[1])
                    else:
                        action_inputs = resp_json.get("action_input", ["0", "0"])
                        await self.type_text(action_inputs[0], action_inputs[1])
                elif resp_json["action"] == "go_to_url":
                    ic("Going to URL")
                    action_inputs = resp_json.get("action_input", "https://google.com")
                    await self.go_to_page(action_inputs)

            except Exception as e:
                ic(response.json())
                ic(f'Exception Reason : {e}')
                notDone = False
