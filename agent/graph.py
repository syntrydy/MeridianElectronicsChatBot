from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

from agent.guardrails import GUARDRAILS
from agent.llm import get_llm
from agent.prompts import get_system_prompt
from agent.tools import load_mcp_tools


async def build_agent() -> CompiledStateGraph:
    llm = get_llm()
    tools = await load_mcp_tools()
    prompt = get_system_prompt()

    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=prompt.prompt,
        middleware=GUARDRAILS,
        checkpointer=MemorySaver(),
    )
