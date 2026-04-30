"""Code-enforced guardrails on top of the system prompt.

These middlewares short-circuit tool calls before they execute. The auth gate
and price-tampering rule are derived from the message history, so they hold
even if the LLM is convinced (via prompt injection or otherwise) to skip them.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from langchain.agents.middleware import ToolCallRequest, wrap_tool_call
from langchain_core.messages import ToolMessage

CUSTOMER_SCOPED_TOOLS = frozenset(
    {"list_orders", "get_order", "get_customer", "create_order"}
)

PRICE_PATTERN = re.compile(r"\[([A-Z]+-\d+)\][^\n]*\n[^\n]*Price:\s*\$([\d.]+)")


def _is_authenticated(messages: list[Any]) -> bool:
    """True if a verify_customer_pin ToolMessage succeeded earlier in this thread."""
    for m in messages:
        if (
            isinstance(m, ToolMessage)
            and m.name == "verify_customer_pin"
            and m.status != "error"
        ):
            return True
    return False


def _reject(request: ToolCallRequest, reason: str) -> ToolMessage:
    return ToolMessage(
        content=f"REJECTED by guardrail: {reason}",
        tool_call_id=request.tool_call["id"],
        name=request.tool_call["name"],
        status="error",
    )


def _messages(request: ToolCallRequest) -> list[Any]:
    return (
        request.state["messages"]
        if isinstance(request.state, dict)
        else getattr(request.state, "messages", [])
    )


@wrap_tool_call
async def require_auth(
    request: ToolCallRequest, handler: Callable[[ToolCallRequest], Any]
) -> ToolMessage:
    """Block customer-scoped tools until verify_customer_pin has succeeded."""
    if request.tool_call["name"] not in CUSTOMER_SCOPED_TOOLS:
        return await handler(request)

    if _is_authenticated(_messages(request)):
        return await handler(request)

    return _reject(
        request,
        f"{request.tool_call['name']} requires authentication. "
        "Call verify_customer_pin(email, pin) first.",
    )


def _known_prices(messages: list[Any]) -> dict[str, Decimal]:
    """Parse {SKU: price} from prior get_product / list_products / search_products outputs."""
    prices: dict[str, Decimal] = {}
    for m in messages:
        if not isinstance(m, ToolMessage) or m.status == "error":
            continue
        if m.name not in ("get_product", "list_products", "search_products"):
            continue
        text = m.content if isinstance(m.content, str) else str(m.content)
        for sku, price_str in PRICE_PATTERN.findall(text):
            try:
                prices[sku] = Decimal(price_str)
            except InvalidOperation:
                continue
    return prices


@wrap_tool_call
async def validate_order_prices(
    request: ToolCallRequest, handler: Callable[[ToolCallRequest], Any]
) -> ToolMessage:
    """Reject create_order if any item's unit_price wasn't seen from a prior product lookup."""
    if request.tool_call["name"] != "create_order":
        return await handler(request)

    items = request.tool_call["args"].get("items") or []
    known = _known_prices(_messages(request))

    for item in items:
        sku = item.get("sku")
        try:
            stated = Decimal(str(item.get("unit_price")))
        except (InvalidOperation, TypeError):
            return _reject(request, f"unit_price for {sku!r} is not a valid decimal")

        if sku not in known:
            return _reject(
                request,
                f"unit_price for {sku!r} cannot be verified — "
                f"call get_product({sku!r}) first to fetch the authoritative price.",
            )
        if stated != known[sku]:
            return _reject(
                request,
                f"unit_price mismatch for {sku!r}: stated ${stated}, "
                f"authoritative ${known[sku]} from get_product. "
                f"Use the product's current price.",
            )

    return await handler(request)


GUARDRAILS = [require_auth, validate_order_prices]
