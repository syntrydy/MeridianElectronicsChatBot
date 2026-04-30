"""Mocked, fast: pin the graph wiring without touching network/LLM."""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from tests.conftest import ai_text, ai_tool_call


async def _ainvoke(agent, text: str, thread_id: str = "t1"):
    return await agent.ainvoke(
        {"messages": [HumanMessage(content=text)]},
        config={"configurable": {"thread_id": thread_id}},
    )


async def test_anonymous_product_query_runs_tool(
    patched_build_agent, fake_llm_factory, tool_calls
):
    llm = fake_llm_factory(
        [
            ai_tool_call("search_products", {"query": "keyboard"}),
            ai_text("We have 5 keyboards. Want details?"),
        ]
    )
    agent = await patched_build_agent(llm)

    out = await _ainvoke(agent, "Do you sell keyboards?")

    assert tool_calls == [("search_products", {"query": "keyboard"})]
    tool_msgs = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert "Found 5 products" in tool_msgs[0].content
    assert out["messages"][-1].content == "We have 5 keyboards. Want details?"


async def test_create_order_uses_price_from_get_product(
    patched_build_agent, fake_llm_factory, stub_responses, tool_calls
):
    """The prompt rule ('unit_price from get_product, never user') is LLM-enforced.
    Here we verify the WIRING — the LLM can chain get_product → create_order, and
    the create_order tool actually receives the args the LLM produced. A regression
    where the graph drops or rewrites tool args would fail this test.
    """
    stub_responses["get_product"] = "[MON-0054] 24-inch Monitor - Model D\n  Price: $166.85 | Stock: 9"
    stub_responses["create_order"] = "Order ord-789 created: status=submitted"

    llm = fake_llm_factory(
        [
            ai_tool_call("verify_customer_pin", {"email": "a@b.c", "pin": "1234"}, "v1"),
            ai_tool_call("get_product", {"sku": "MON-0054"}, "g1"),
            ai_tool_call(
                "create_order",
                {
                    "customer_id": "cust-123",
                    "items": [
                        {
                            "sku": "MON-0054",
                            "quantity": 1,
                            "unit_price": "166.85",
                            "currency": "USD",
                        }
                    ],
                },
                "c1",
            ),
            ai_text("Order ord-789 confirmed."),
        ]
    )
    agent = await patched_build_agent(llm)

    out = await _ainvoke(agent, "Order one MON-0054 please. Email a@b.c, PIN 1234.")

    names = [name for name, _ in tool_calls]
    assert names == ["verify_customer_pin", "get_product", "create_order"]

    create_args = dict(tool_calls[2][1])
    assert create_args["customer_id"] == "cust-123"
    assert create_args["items"][0]["sku"] == "MON-0054"
    assert create_args["items"][0]["unit_price"] == "166.85"
    assert "ord-789" in out["messages"][-1].content


async def test_tool_error_surfaces_to_llm_as_tool_message(
    patched_build_agent, fake_llm_factory, stub_responses, tool_calls
):
    from langchain_core.tools import ToolException

    stub_responses["get_product"] = ToolException(
        "Product with SKU 'BOGUS' not found"
    )

    llm = fake_llm_factory(
        [
            ai_tool_call("get_product", {"sku": "BOGUS"}),
            ai_text("Sorry, I couldn't find that SKU."),
        ]
    )
    agent = await patched_build_agent(llm)
    out = await _ainvoke(agent, "Look up SKU BOGUS")

    tool_msgs = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].status == "error"
    assert "BOGUS" in tool_msgs[0].content
    assert out["messages"][-1].content == "Sorry, I couldn't find that SKU."


async def test_session_isolation(patched_build_agent, fake_llm_factory):
    """Two thread_ids = two independent histories, served by the same graph."""
    llm = fake_llm_factory(
        [ai_text("a-1"), ai_text("b-1"), ai_text("a-2")]
    )
    agent = await patched_build_agent(llm)

    out_a = await _ainvoke(agent, "hello", thread_id="thread-A")
    out_b = await _ainvoke(agent, "hello", thread_id="thread-B")

    assert [m.content for m in out_a["messages"]] == ["hello", "a-1"]
    assert [m.content for m in out_b["messages"]] == ["hello", "b-1"]

    out_a2 = await agent.ainvoke(
        {"messages": [HumanMessage(content="follow up")]},
        config={"configurable": {"thread_id": "thread-A"}},
    )
    contents = [m.content for m in out_a2["messages"]]
    assert contents == ["hello", "a-1", "follow up", "a-2"]
    assert "b-1" not in contents


