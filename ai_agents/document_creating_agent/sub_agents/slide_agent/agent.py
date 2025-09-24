import os
from google.adk import Agent

from . import prompt
from .tools import get_tools

model = os.getenv("ROOT_AGENT_MODEL", "gemini-2.5-flash")

slide_agent = Agent(
    name="slide_agent",
    model=model,
    instruction=prompt.SLIDE_PROMPT,
    tools=[
        *get_tools(),
    ],
)
