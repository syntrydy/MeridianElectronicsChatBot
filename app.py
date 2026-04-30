import asyncio
import logging

from dotenv import load_dotenv

load_dotenv()

import gradio as gr

from agent.graph import build_agent
from agent.prompts import get_system_prompt
from config import get_settings
from observability import (
    configure_logging,
    get_langfuse_handler,
    get_tool_call_logger,
)

settings = get_settings()
configure_logging(settings.log_level)
LOG = logging.getLogger("app")

LOG.info("building agent")
AGENT = asyncio.run(build_agent())
LOG.info("agent ready")


async def chat_fn(message: str, history: list[dict], request: gr.Request) -> str:
    config = {
        "configurable": {"thread_id": request.session_hash},
        "callbacks": [get_langfuse_handler(), get_tool_call_logger()],
        "metadata": {"langfuse_prompt": get_system_prompt()},
    }
    result = await AGENT.ainvoke(
        {"messages": [{"role": "user", "content": message}]},
        config=config,
    )
    return result["messages"][-1].content


demo = gr.ChatInterface(
    fn=chat_fn,
    title="Meridian Electronics Support",
    description="Ask about products, look up your orders, or place a new order.",
    examples=[
        "Do you sell mechanical keyboards?",
        "I'd like to check my recent orders.",
        "I want to order a 27-inch monitor.",
        "Can I return an item I bought last week?",
    ],
)


if __name__ == "__main__":
    demo.launch()
