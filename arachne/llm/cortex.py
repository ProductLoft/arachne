import json

import boto3
from regex import regex

import structlog

from arachne.llm.aws import LLM

log = structlog.get_logger()

'''
Cortex functions as the decision engine for the agent.
Given a prompt or a situation cortex will decide the next step.
'''


class Cortex:

    def __init__(self):
        self.llm = LLM()

    def plan(self, prompt):
        prompt = f'''
        Agent performing agentic action on the web.
        Need to plan the steps to achieve the goal.
        plan should be a list of subgoals to achieve to reach the goal.
        
        the subgoals should be provided as a json object.

        '''

        resp =  self.llm.get_json_response(prompt)

        return resp
