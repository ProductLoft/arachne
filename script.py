import asyncio
import io
from datetime import datetime

from regex import regex
import json

from playwright.async_api import async_playwright

from arachne.agent import WebWeaver

import base64
from PIL import Image
import requests


async def _main():
    with open(".env", "r") as f:
        # OpenAI API Key
        api_key = f.read()


    # Function to encode the image
    def encode_image(input_image: Image, height=2048):

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

    async def read_page() -> str:
        """
        Use to read the current state of the page
        """
        return await read_page_impl()

    async def go_to_page(url: str) -> [Image]:
        await page.goto(url)
        return await read_page_impl()

    async def read_page_impl() -> [Image]:
        image, inner_tag_to_xpath = await ww.page_to_image(page)
        tag_to_xpath.clear()
        tag_to_xpath.update(inner_tag_to_xpath)
        return encode_image(image)

    async def click(element_id: int) -> str:
        """
        Click on an element based on element_id and return the new page state
        """
        print(element_id)
        print(type(element_id))
        x_path = tag_to_xpath[element_id]
        print(x_path)
        element = page.locator(x_path)
        await element.scroll_into_view_if_needed()
        await page.wait_for_timeout(1000)
        await element.click()
        await page.wait_for_timeout(2000)
        return await read_page_impl()

    async def type_text(element_id: int, text: str) -> str:
        """
        Input text into a textbox based on element_id and return the new page state
        """
        x_path = tag_to_xpath[element_id]
        print(x_path)
        await page.locator(x_path).press_sequentially(text)
        return await read_page_impl()

    async def press_key(key: str) -> str:
        """
        Press a key on the keyboard and return the new page state
        """
        await page.keyboard.press(key)
        await page.wait_for_timeout(2000)
        return await read_page_impl()

    p = await async_playwright().__aenter__()
    browser = await p.chromium.launch(headless=False)
    page = await browser.new_page()


    # with open("config.json", "r") as f:
    #     google_cloud_credentials = json.load(f)

    ww = WebWeaver()
    tag_to_xpath = {}
    tasks_history = []

    question = ""

    site_name = "https://reddit.com"

    await page.goto("https://reddit.com")

    print(type(page))

    screenshot, tag_to_xpath = await ww.page_to_image(page)

    screenshot_buffer = io.BytesIO(screenshot)
    images = encode_image(Image.open(screenshot_buffer))
    notDone = True


    while notDone:

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
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
                        }, *images
                    ]
                }
            ],
            "max_tokens": 10000,
        }
        # resp[0]
        #
        print(payload)
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        try:
            resp = response.json()["choices"][0]["message"]["content"]
            pattern = regex.compile(r'\{(?:[^{}]|(?R))*\}')
            resp_content = pattern.findall(resp)
            resp_json = json.loads(resp_content[0])
            print("resp_json",resp_json)

            if "final_answer" in resp:
                notDone = False
            else:
                tasks_history.append(resp_json)

            if resp_json["action"] == "read_page":
                print("Reading Page")
                await read_page()
            elif resp_json["action"] == "click":
                print("Clicking")
                action_inputs = resp_json.get("action_input", 0)
                await click(int(action_inputs))
            elif resp_json["action"] == "type_text":
                print("Typing")
                action_inputs = resp_json.get("action_input", ["0", "0"])
                await type_text(action_inputs[0], action_inputs[1])
            elif resp_json["action"] == "go_to_url":
                print("Going to URL")
                action_inputs = resp_json.get("action_input", "https://google.com")
                await go_to_page(action_inputs)

        except Exception as e:
            print(response.json())
            print(f'Exception Reason : {e}')
            notDone = False


asyncio.run(_main())