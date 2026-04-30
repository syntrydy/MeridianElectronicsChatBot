# Architecture

## Runtime flow

```mermaid
flowchart LR
    User([Customer])

    subgraph Runner["AWS App Runner instance (1 vCPU / 2 GB, min=max=1)"]
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

## Deploy pipeline (AWS App Runner)

```mermaid
flowchart LR
    Dev([Developer])

    subgraph Local["Local"]
        Build["build.sh<br/>git ls-files → zip"]
    end

    subgraph AWS["AWS account"]
        S3[(S3<br/>source bucket)]
        CB["CodeBuild project<br/>aws/codebuild/standard:7.0<br/>privileged · BUILD_GENERAL1_SMALL"]
        ECR[(ECR<br/>meridian-bot)]
        Service["App Runner service<br/>meridian-bot"]
        SM[(Secrets Manager<br/>meridian/*)]
    end

    Dev -->|terraform apply<br/>build.sh| Build
    Build -->|aws s3 cp| S3
    Build -->|start-build| CB
    S3 --> CB
    CB -->|docker build + push| ECR
    Dev -->|terraform apply<br/>image_tag=&lt;sha&gt;| Service
    ECR --> Service
    SM -.runtime secrets.-> Service
```

Three phases per deploy: targeted `terraform apply` for the AWS skeleton (one-time), `build.sh` for image build (~80s), full `terraform apply` to roll the service forward (~3 min).

## Trust boundaries

```mermaid
flowchart TB
    subgraph Public["Public (untrusted)"]
        U[Customer browser]
    end
    subgraph Runner["AWS App Runner (semi-trusted, public URL)"]
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

Dashed border on the App Runner box marks the **production gaps** documented in `CLAUDE.md`: no bot-side auth, no rate limiting, in-process session store (pinned `min=max=1` to compensate), Langfuse PII redaction unresolved.
