"""Code-enforced guardrails: auth gate + price-tampering rejection.

These pin the rules that the prompt only guides — a regression here
means a prompt-injection attacker could place a bogus order or read
another customer's data.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, ToolMessage

from tests.conftest import ai_text, ai_tool_call


async def _ainvoke(agent, text: str, thread_id: str = "g1"):
    return await agent.ainvoke(
        {"messages": [HumanMessage(content=text)]},
        config={"configurable": {"thread_id": thread_id}},
    )


async def test_list_orders_blocked_without_auth(
    patched_build_agent, fake_llm_factory, tool_calls
):
    llm = fake_llm_factory(
        [
            ai_tool_call("list_orders", {}),
            ai_text("I need to authenticate you first."),
        ]
    )
    agent = await patched_build_agent(llm)

    out = await _ainvoke(agent, "Show me my orders.")

    assert tool_calls == [], (
        f"Tool was executed despite guardrail. tool_calls={tool_calls}"
    )
    tool_msgs = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].status == "error"
    assert "REJECTED by guardrail" in tool_msgs[0].content
    assert "verify_customer_pin" in tool_msgs[0].content


async def test_create_order_blocked_without_auth(
    patched_build_agent, fake_llm_factory, tool_calls
):
    llm = fake_llm_factory(
        [
            ai_tool_call(
                "create_order",
                {
                    "customer_id": "anyone",
                    "items": [
                        {"sku": "MON-0054", "quantity": 1, "unit_price": "166.85", "currency": "USD"}
                    ],
                },
            ),
            ai_text("Auth required."),
        ]
    )
    agent = await patched_build_agent(llm)

    await _ainvoke(agent, "place an order")

    assert tool_calls == [], (
        "create_order ran without auth — guardrail bypassed"
    )


async def test_create_order_rejects_unverified_price(
    patched_build_agent, fake_llm_factory, stub_responses, tool_calls
):
    """LLM tries to create_order with a price that doesn't match get_product."""
    stub_responses["get_product"] = (
        "[MON-0054] 24-inch Monitor - Model D\n"
        "  Category: Monitors | Price: $166.85 | Stock: 9 units"
    )

    llm = fake_llm_factory(
        [
            ai_tool_call("verify_customer_pin", {"email": "a@b.c", "pin": "1234"}, "v1"),
            ai_tool_call("get_product", {"sku": "MON-0054"}, "g1"),
            ai_tool_call(
                "create_order",
                {
                    "customer_id": "cust-1",
                    "items": [
                        {"sku": "MON-0054", "quantity": 1, "unit_price": "1.00", "currency": "USD"}
                    ],
                },
                "c1",
            ),
            ai_text("Sorry, that price didn't match."),
        ]
    )
    agent = await patched_build_agent(llm)
    out = await _ainvoke(agent, "order MON-0054 at $1")

    names = [n for n, _ in tool_calls]
    assert "create_order" not in names, (
        f"create_order ran despite price mismatch. tool_calls={tool_calls}"
    )

    rejection = next(
        m
        for m in out["messages"]
        if isinstance(m, ToolMessage) and m.name == "create_order"
    )
    assert rejection.status == "error"
    assert "mismatch" in rejection.content
    assert "166.85" in rejection.content


async def test_create_order_rejects_sku_without_prior_lookup(
    patched_build_agent, fake_llm_factory, tool_calls
):
    """Place an order for a SKU we never called get_product on — must reject."""
    llm = fake_llm_factory(
        [
            ai_tool_call("verify_customer_pin", {"email": "a@b.c", "pin": "1234"}, "v1"),
            ai_tool_call(
                "create_order",
                {
                    "customer_id": "cust-1",
                    "items": [
                        {"sku": "COM-9999", "quantity": 1, "unit_price": "100.00", "currency": "USD"}
                    ],
                },
                "c1",
            ),
            ai_text("Looking up that SKU first."),
        ]
    )
    agent = await patched_build_agent(llm)
    out = await _ainvoke(agent, "order COM-9999")

    names = [n for n, _ in tool_calls]
    assert "create_order" not in names

    rejection = next(
        m
        for m in out["messages"]
        if isinstance(m, ToolMessage) and m.name == "create_order"
    )
    assert "cannot be verified" in rejection.content


async def test_create_order_passes_when_price_matches_prior_lookup(
    patched_build_agent, fake_llm_factory, stub_responses, tool_calls
):
    """Happy path: auth + get_product + create_order with matching price = allowed."""
    stub_responses["get_product"] = (
        "[ACC-0136] Mechanical Keyboard - Model A\n"
        "  Category: Accessories | Price: $193.37 | Stock: 46 units"
    )
    stub_responses["create_order"] = "Order ord-OK created: status=submitted"

    llm = fake_llm_factory(
        [
            ai_tool_call("verify_customer_pin", {"email": "a@b.c", "pin": "1234"}, "v1"),
            ai_tool_call("get_product", {"sku": "ACC-0136"}, "g1"),
            ai_tool_call(
                "create_order",
                {
                    "customer_id": "cust-1",
                    "items": [
                        {"sku": "ACC-0136", "quantity": 1, "unit_price": "193.37", "currency": "USD"}
                    ],
                },
                "c1",
            ),
            ai_text("Order placed."),
        ]
    )
    agent = await patched_build_agent(llm)
    out = await _ainvoke(agent, "order ACC-0136")

    names = [n for n, _ in tool_calls]
    assert names == ["verify_customer_pin", "get_product", "create_order"]
    create_msg = next(
        m
        for m in out["messages"]
        if isinstance(m, ToolMessage) and m.name == "create_order"
    )
    assert create_msg.status != "error"
    assert "ord-OK" in create_msg.content
