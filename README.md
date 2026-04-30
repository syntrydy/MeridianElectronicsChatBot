# Meridian Electronics Support Chatbot

Customer support chatbot prototype for Meridian Electronics, a computer products retailer. The bot handles product availability lookups, order placement, order history, and returning-customer authentication by delegating to the company's existing systems through an MCP server.

Built as a 3-hour prototype that engineering can take to security review without a rewrite.

## What it does

- Anonymous product search
- Returning-customer authentication, then order history lookup
- New order placement with mid-flow authentication and confirmation
- Graceful refusal of out-of-scope requests (returns, refunds, etc.)

## Architecture

Gradio UI (one session = one `thread_id`) → LangChain `create_agent` (LLM bound to MCP tools, two `wrap_tool_call` middlewares for code-enforced auth + price-tampering guardrails, `MemorySaver` checkpointer) → `langchain-mcp-adapters` Streamable-HTTP client → MCP server. Langfuse `CallbackHandler` attached to every invocation auto-traces LLM and tool spans. Tools load once at startup; if MCP is unreachable at boot, the app exits.

## Stack

| Choice | Why |
|---|---|
| Python | LangGraph / LangChain / MCP SDK ecosystem is most mature in Python |
| gpt-4o-mini | Cheapest tier with reliable tool-calling |
| LangChain `create_agent` | LLM↔tool loop, message state, checkpointing, middleware seam for guardrails — without writing them |
| `langchain-mcp-adapters` | Converts MCP tools to LangChain `BaseTool`s automatically |
| Langfuse | Per-turn traces, token cost, latency |
| `MemorySaver` | In-process session state (production gap: needs Redis/Postgres) |
| Gradio `ChatInterface` | Fastest path to HF Spaces; ships chat UX + session handling |
| HF Spaces (Gradio SDK) | Cheapest deploy path |
| pydantic-settings | Type-safe env config |
| pytest + `FakeMessagesListChatModel` | Ships with LangChain, no extra mocking |

## Project layout

```
meridian-bot/
├── app.py                # Gradio entry, session→thread_id mapping
├── agent/
│   ├── graph.py          # build_agent() — wires llm + tools + system + middleware + checkpointer
│   ├── llm.py            # get_llm() — ChatOpenAI from env
│   ├── tools.py          # load_mcp_tools() — async, called at startup
│   ├── prompts.py        # get_system_prompt() — Langfuse-managed, local fallback
│   └── guardrails.py     # require_auth, validate_order_prices middlewares
├── scripts/
│   └── seed_prompt.py    # one-off: push SYSTEM_PROMPT to Langfuse as version 1
├── observability.py      # JSON logging, Langfuse handler, tool-call logger
├── config.py             # Settings (pydantic-settings)
├── tests/
│   ├── test_graph.py     # mocked: graph wiring
│   ├── test_guardrails.py# mocked: code-enforced auth + price rules
│   ├── test_smoke.py     # @pytest.mark.smoke — live MCP + OpenAI
│   └── test_data.py      # seeded customer credentials
├── .env.example
├── requirements.txt      # HF Spaces (Gradio SDK) reads this
├── pyproject.toml
└── README.md
```

## Configuration

Copy `.env.example` to `.env` and fill in the values.

| Variable | Required | Default |
|---|---|---|
| `OPENAI_API_KEY` | yes | — |
| `OPENAI_MODEL` | no | `gpt-4o-mini` |
| `MCP_SERVER_URL` | yes | — |
| `MCP_REQUEST_TIMEOUT` | no | `30` |
| `LANGFUSE_PUBLIC_KEY` | yes | — |
| `LANGFUSE_SECRET_KEY` | yes | — |
| `LANGFUSE_HOST` | no | `https://cloud.langfuse.com` |
| `LOG_LEVEL` | no | `INFO` |
| `ENVIRONMENT` | no | `development` |

## Run

```bash
uv sync                              # or: pip install -r requirements.txt
cp .env.example .env                 # fill in keys
python -m scripts.seed_prompt        # one-off: push SYSTEM_PROMPT to Langfuse
python app.py
```

## Test

```bash
pytest                 # mocked, fast
pytest -m smoke        # hits real MCP
```

## Deploy

AWS App Runner (Terraform + Docker). See [`deploy/aws-apprunner/README.md`](deploy/aws-apprunner/README.md) for the runbook. The four secrets (`OPENAI_API_KEY`, `MCP_SERVER_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`) are wired through Terraform variables, not committed.

## Conventions

- Async end-to-end (`ainvoke`, async tool loader)
- Tools loaded once at startup, never re-fetched per turn
- One static system prompt, ~400 tokens
- `thread_id = gr.Request.session_hash`; `MemorySaver` owns history
- Retry at the lowest layer that can meaningfully retry — never double-retry
- Logs are stdout JSON: tool name, latency, outcome. **Never log tool args or results** (PII)

## Out of scope (v1)

Persistent storage · streaming UX · custom `StateGraph` · pre-tool interrupts · bot-side auth · rate limiting · multi-language · voice · email/SMS channels · admin dashboard · A/B framework · eval harness beyond smoke tests.

## Production gaps (handoff list)

1. In-process session store — needs Redis/Postgres
2. No human-in-the-loop interrupt before destructive tools (code-enforced guardrails + system prompt; no UI confirm step)
3. No bot-side auth — HF Space is public
4. No rate limiting / abuse prevention
5. Langfuse traces may contain PII — needs redaction policy + retention/region decision
6. No cost alarms
7. Prompt injection: code-enforced guardrails block unauthenticated customer-scoped tools and unverified prices; broader injection (e.g. malicious MCP responses steering tool selection) still needs review
