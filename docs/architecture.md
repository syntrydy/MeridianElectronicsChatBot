# Architecture

## Runtime flow

```mermaid
flowchart LR
    User([Customer])

    subgraph HF["HF Space (Gradio SDK)"]
        UI["Gradio ChatInterface<br/>session_hash → thread_id"]
    end

    subgraph App["Python app (app.py)"]
        Agent["LangGraph<br/>create_react_agent"]
        Mem[("MemorySaver<br/>(in-process)")]
        LLM["ChatOpenAI<br/>gpt-4o-mini"]
        Adapter["langchain-mcp-adapters<br/>(Streamable HTTP client)"]
        CB["Langfuse CallbackHandler"]
    end

    subgraph Meridian["Meridian backend"]
        MCP["MCP Server"]
        Sys[("Catalog · Orders · Auth")]
    end

    LF[(Langfuse Cloud)]
    OAI[(OpenAI API)]

    User <--> UI
    UI <--> Agent
    Agent <--> Mem
    Agent <--> LLM
    Agent <--> Adapter
    Adapter <--> MCP
    MCP <--> Sys
    LLM <--> OAI
    CB -.traces.-> LF
    Agent -.per invocation.-> CB
```

## Startup vs. per-turn

```mermaid
sequenceDiagram
    autonumber
    participant Boot as app.py (boot)
    participant Tools as load_mcp_tools()
    participant MCP as MCP Server
    participant Build as build_agent()

    Boot->>Tools: async fetch tool schemas
    Tools->>MCP: list tools (Streamable HTTP)
    MCP-->>Tools: tool definitions
    Tools-->>Boot: LangChain BaseTool[]
    Boot->>Build: llm + tools + system_prompt + MemorySaver
    Build-->>Boot: compiled agent
    Note over Boot: If MCP unreachable → exit(1)

    participant U as User
    participant UI as Gradio
    participant A as Agent
    participant L as LLM
    participant T as Tool (via MCP)
    participant LF as Langfuse

    U->>UI: message
    UI->>A: ainvoke(thread_id=session_hash)
    A->>L: messages + tool schemas
    L-->>A: tool_call
    A->>T: invoke(args)
    T-->>A: result
    A->>L: messages + tool result
    L-->>A: final answer
    A-->>UI: response
    A-)LF: spans (LLM + tool, async)
    UI-->>U: reply
```

## Key invariants

- **Async end-to-end** — no sync/async mixing
- **Tools loaded once** at startup; never re-fetched per turn
- **One static system prompt** (~400 tokens) — no per-turn dynamic content
- **`thread_id = gr.Request.session_hash`** — `MemorySaver` owns history
- **Auth is MCP-side** — bot trusts the server to enforce it
- **Logs never contain tool args or results** (PII)

## Trust boundaries

```mermaid
flowchart TB
    subgraph Public["Public (untrusted)"]
        U[Customer browser]
    end
    subgraph Space["HF Space (semi-trusted, public URL)"]
        G[Gradio + Agent]
    end
    subgraph Meridian["Meridian network (trusted)"]
        M[MCP Server]
        B[Backend systems]
    end

    U -- HTTPS --> G
    G -- HTTPS + auth headers --> M
    M --> B

    classDef gap stroke-dasharray: 4 4,stroke:#c00
    class G gap
```

Dashed border on the Space marks the **production gaps** documented in `CLAUDE.md`: no bot-side auth, no rate limiting, in-process session store, Langfuse PII redaction unresolved.
