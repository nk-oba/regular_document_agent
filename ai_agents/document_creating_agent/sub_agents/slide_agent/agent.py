import os
from google.adk import Agent

from . import prompt
from .tools import get_tools

# モデル名を安全に取得
model = os.getenv("ROOT_AGENT_MODEL")
if not model:
    model = "gemini-1.5-flash"

slide_agent = Agent(
    name="slide_agent",
    model=model,
    instruction=prompt.SLIDE_PROMPT,
    tools=[
        *get_tools(),
    ],
)
