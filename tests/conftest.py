"""Shared fixtures: build_agent() with no network — fake LLM, stub MCP tools, local prompt."""

from __future__ import annotations

from typing import Any

import pytest
from dataclasses import dataclass

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field

from agent import graph as graph_module
from agent.prompts import SYSTEM_PROMPT


@dataclass
class _PromptStub:
    prompt: str


class ToolBindingFakeChatModel(FakeMessagesListChatModel):
    """FakeMessagesListChatModel + a no-op bind_tools so create_agent accepts it."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: D401, ANN001
        return self


class _ListProductsArgs(BaseModel):
    category: str | None = Field(default=None)
    is_active: bool | None = Field(default=None)


class _GetProductArgs(BaseModel):
    sku: str


class _SearchProductsArgs(BaseModel):
    query: str


class _GetCustomerArgs(BaseModel):
    customer_id: str


class _VerifyCustomerPinArgs(BaseModel):
    email: str
    pin: str


class _ListOrdersArgs(BaseModel):
    customer_id: str | None = Field(default=None)
    status: str | None = Field(default=None)


class _GetOrderArgs(BaseModel):
    order_id: str


class _CreateOrderArgs(BaseModel):
    customer_id: str
    items: list[dict[str, Any]]


@pytest.fixture
def tool_calls() -> list[tuple[str, dict[str, Any]]]:
    """Mutable list each fake tool appends to on invocation. Tests assert against this."""
    return []


@pytest.fixture
def stub_responses() -> dict[str, Any]:
    """Per-tool stubbed return values. Tests override to inject errors or specific outputs."""
    return {
        "list_products": "Found 200 products...",
        "get_product": "[COM-0001] Desktop\n  Price: $999.00 | Stock: 10 units",
        "search_products": "Found 5 products matching '...'",
        "get_customer": "Customer details...",
        "verify_customer_pin": "Customer verified: id=cust-123, name=Alice",
        "list_orders": "Found 3 orders...",
        "get_order": "Order details...",
        "create_order": "Order created: id=ord-456, status=submitted",
    }


def _make_tool(
    name: str,
    description: str,
    args_schema: type[BaseModel],
    tool_calls: list[tuple[str, dict[str, Any]]],
    stub_responses: dict[str, Any],
) -> StructuredTool:
    def _fn(**kwargs: Any) -> str:
        tool_calls.append((name, kwargs))
        result = stub_responses[name]
        if isinstance(result, BaseException):
            raise result
        return result

    tool = StructuredTool.from_function(
        func=_fn,
        name=name,
        description=description,
        args_schema=args_schema,
    )
    tool.handle_tool_error = True
    return tool


@pytest.fixture
def fake_tools(
    tool_calls: list[tuple[str, dict[str, Any]]],
    stub_responses: dict[str, Any],
) -> list[StructuredTool]:
    specs = [
        ("list_products", "List products with optional filters.", _ListProductsArgs),
        ("get_product", "Get product by SKU.", _GetProductArgs),
        ("search_products", "Search products by name or description.", _SearchProductsArgs),
        ("get_customer", "Get customer by ID.", _GetCustomerArgs),
        ("verify_customer_pin", "Verify customer email + PIN.", _VerifyCustomerPinArgs),
        ("list_orders", "List orders.", _ListOrdersArgs),
        ("get_order", "Get order by ID.", _GetOrderArgs),
        ("create_order", "Create a new order.", _CreateOrderArgs),
    ]
    return [_make_tool(n, d, s, tool_calls, stub_responses) for n, d, s in specs]


@pytest.fixture
def fake_llm_factory():
    """Returns a builder that wraps a script of AIMessages into a FakeMessagesListChatModel."""

    def _build(responses: list[BaseMessage]) -> ToolBindingFakeChatModel:
        return ToolBindingFakeChatModel(responses=responses)

    return _build


@pytest.fixture
def patched_build_agent(
    monkeypatch: pytest.MonkeyPatch, fake_tools: list[StructuredTool]
):
    """build_agent() with patched dependencies — no network, no API keys."""

    def _factory(llm):
        async def _load_tools():
            return fake_tools

        def _get_llm():
            return llm

        def _get_prompt():
            return _PromptStub(prompt=SYSTEM_PROMPT)

        monkeypatch.setattr(graph_module, "load_mcp_tools", _load_tools)
        monkeypatch.setattr(graph_module, "get_llm", _get_llm)
        monkeypatch.setattr(graph_module, "get_system_prompt", _get_prompt)
        return graph_module.build_agent()

    return _factory


def ai_tool_call(name: str, args: dict[str, Any], call_id: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def ai_text(text: str) -> AIMessage:
    return AIMessage(content=text)
