
from arachne.llm.cortex import Cortex


'''
A WeaverAgent is designed to navigate the web autonomously.
Given a prompt and a goal. Weaver will plot a course to the goal.
This involves designing the steps that are involved and then taking actions on them.
'''

class Step:
    def __init__(self):
        self.description = None
        self.action = None
        self.status = None


class WeaverAgent:
    def __init__(self, prompt, name):
        self.prompt = prompt
        self.cortex  = Cortex()
        self.task_name = None
        self.steps = self.steps_from_prompt(prompt)
        self.current_step = 0
        self.current_page = None

    def steps_from_prompt(self, prompt):
        self.steps, self.task_name = self.cortex.get_steps(prompt)

    def run(self):
        for step in self.steps:
            self.current_page = step.run(self.current_page)
            if self.current_page is None:
                break
        return self.current_page
