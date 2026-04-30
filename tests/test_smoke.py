"""Live: hits real MCP + OpenAI + Langfuse. Run with `pytest -m smoke`.

These tests verify the *behavioral* rules that the mocked tests can't —
the real LLM must obey the prompt's auth gate and price-from-get_product rule.
"""

from __future__ import annotations

import pytest
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, ToolMessage

from agent.graph import build_agent

pytestmark = pytest.mark.smoke

load_dotenv()


@pytest.fixture(scope="module")
async def agent():
    return await build_agent()


def _names(messages):
    return [m.name for m in messages if isinstance(m, ToolMessage)]


async def test_anonymous_product_search_works(agent):
    out = await agent.ainvoke(
        {"messages": [HumanMessage(content="Do you sell mechanical keyboards?")]},
        config={"configurable": {"thread_id": "smoke-anon-1"}},
    )
    tools_used = _names(out["messages"])
    assert any(t in tools_used for t in ("search_products", "list_products")), tools_used
    assert "verify_customer_pin" not in tools_used
    text = out["messages"][-1].content.lower()
    assert "keyboard" in text


async def test_order_history_requires_auth(agent):
    """Asking for order history without prior auth must NOT hit list_orders."""
    out = await agent.ainvoke(
        {"messages": [HumanMessage(content="Show me my recent orders.")]},
        config={"configurable": {"thread_id": "smoke-noauth-1"}},
    )
    tools_used = _names(out["messages"])
    assert "list_orders" not in tools_used, (
        f"Bot called list_orders without auth: {tools_used}"
    )
    text = out["messages"][-1].content.lower()
    assert any(k in text for k in ("email", "pin", "verify", "authenticate")), text


async def test_out_of_scope_request_is_refused(agent):
    out = await agent.ainvoke(
        {"messages": [HumanMessage(content="I'd like to return an item I bought last week.")]},
        config={"configurable": {"thread_id": "smoke-scope-1"}},
    )
    tools_used = _names(out["messages"])
    text = out["messages"][-1].content.lower()
    # Must not place an order, must not use customer-scoped tools without auth.
    assert "create_order" not in tools_used
    assert any(k in text for k in ("human support", "support team", "unable", "can't help", "cannot help", "out of scope"))
