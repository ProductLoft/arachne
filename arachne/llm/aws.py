import json

import boto3
from regex import regex

from logs import logger


class LLM:
    def __init__(self):
        self.brt = boto3.client(service_name='bedrock-runtime')
        self.modelId = 'anthropic.claude-v2'
        self.accept = 'application/json'
        self.contentType = 'application/json'
        self.prompt = ''
        self.body = {
            "max_tokens": 4000,
            "temperature": 0.1,
            "anthropic_version": "bedrock-2023-05-31",
            "top_p": 0.9,
        }

    async def call_llm(self, prompt):

        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": f'{prompt}'
                             }],
            }
        ]

        self.body["messages"] = messages

        response = self.brt.invoke_model(body=json.dumps(self.body), modelId=self.modelId, accept=self.accept,
                                         contentType=self.contentType)

        logger.info(f'response {response}')
        response_body = json.loads(response.get('body').read())
        logger.info(f'response_body, {response_body}')

        # text
        logger.info(f'response_body.get {response_body["content"][0]["text"]}')

        return response_body['content'][0]['text']

    async def get_json_response(self, prompt):

        await self.call_llm(prompt)
        output = await self.call_llm(prompt)

        pattern = regex.compile(r'\{(?:[^{}]|(?R))*\}')
        resp = pattern.findall(output)

        try:
            return json.loads(resp[0])
        except Exception as e:
            logger.info(f'json decoding failed with error: {e}')
            return None