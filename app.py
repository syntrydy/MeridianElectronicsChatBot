import asyncio
import base64
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


LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36" width="36" height="36" aria-hidden="true">
  <defs>
    <linearGradient id="meGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#6366f1"/>
      <stop offset="100%" stop-color="#4338ca"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="36" height="36" rx="9" fill="url(#meGrad)"/>
  <path d="M8 26 V10 L18 22 L28 10 V26" fill="none" stroke="#ffffff" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>
</svg>"""

ASSISTANT_AVATAR = (
    "data:image/svg+xml;base64,"
    + base64.b64encode(LOGO_SVG.encode("utf-8")).decode("ascii")
)

HEADER_HTML = f"""
<div class="me-header">
  <div class="me-logo">{LOGO_SVG}</div>
  <div class="me-brand">
    <h1>Meridian Electronics</h1>
    <p class="tagline">Computer Products &amp; Support</p>
  </div>
</div>
"""

FOOTER_HTML = """
<div class="me-footer">
  © Meridian Electronics · prototype · for support beyond orders, please contact a human agent
</div>
"""

EXAMPLES = [
    "Do you sell mechanical keyboards?",
    "I'd like to check my recent orders.",
    "I want to order a 27-inch monitor.",
    "Can I return an item I bought last week?",
]

BRAND_THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.indigo,
    secondary_hue=gr.themes.colors.emerald,
    neutral_hue=gr.themes.colors.slate,
    radius_size=gr.themes.sizes.radius_lg,
    spacing_size=gr.themes.sizes.spacing_md,
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui"],
).set(
    body_background_fill="*neutral_50",
    body_background_fill_dark="*neutral_950",
    block_background_fill="white",
    block_background_fill_dark="*neutral_900",
    button_primary_background_fill="*primary_600",
    button_primary_background_fill_hover="*primary_700",
    button_primary_text_color="white",
)

BRAND_CSS = """
.gradio-container { max-width: 920px !important; margin: 0 auto !important; }

.me-header {
  display: flex; align-items: center; gap: 14px;
  padding: 18px 4px 16px 4px;
  border-bottom: 1px solid var(--border-color-primary);
  margin-bottom: 18px;
}
.me-logo { display: flex; }
.me-logo svg { display: block; }
.me-brand h1 {
  margin: 0; font-size: 1.25rem; font-weight: 600;
  letter-spacing: -0.01em; color: var(--body-text-color);
}
.me-brand .tagline {
  margin: 2px 0 0; font-size: 0.875rem; color: var(--body-text-color-subdued);
}

#me-chat { border-radius: var(--radius-lg); box-shadow: 0 1px 3px rgba(15,23,42,0.06); }

.me-inputrow { gap: 10px; align-items: stretch; margin-top: 12px; }
.me-send { min-width: 96px; font-weight: 600; }

.me-examples { margin-top: 8px; }
.me-examples .gr-examples-table button,
.me-examples button {
  border-radius: 999px !important;
  padding: 6px 14px !important;
  background: var(--neutral-100) !important;
  border: 1px solid var(--border-color-primary) !important;
  font-weight: 500 !important;
  transition: background 120ms ease, border-color 120ms ease;
}
.me-examples button:hover {
  background: var(--primary-50) !important;
  border-color: var(--primary-200) !important;
}

.me-footer {
  text-align: center; font-size: 0.75rem;
  color: var(--body-text-color-subdued);
  padding: 18px 0 6px 0;
}
"""


async def respond(message: str, history: list[dict], request: gr.Request):
    if not message or not message.strip():
        return "", history
    history = history + [{"role": "user", "content": message}]
    config = {
        "configurable": {"thread_id": request.session_hash},
        "callbacks": [get_langfuse_handler(), get_tool_call_logger()],
        "metadata": {"langfuse_prompt": get_system_prompt()},
    }
    result = await AGENT.ainvoke(
        {"messages": [{"role": "user", "content": message}]},
        config=config,
    )
    history = history + [
        {"role": "assistant", "content": result["messages"][-1].content}
    ]
    return "", history


with gr.Blocks(
    title="Meridian Electronics Support",
    fill_height=False,
) as demo:
    gr.HTML(HEADER_HTML)

    chatbot = gr.Chatbot(
        elem_id="me-chat",
        height=560,
        avatar_images=(None, ASSISTANT_AVATAR),
        placeholder=(
            "<strong>How can we help?</strong><br/>"
            "Ask about products, orders, or your account."
        ),
        render_markdown=True,
        show_label=False,
    )

    with gr.Row(elem_classes=["me-inputrow"]):
        msg = gr.Textbox(
            placeholder="Message Meridian Support...",
            scale=9,
            show_label=False,
            autofocus=True,
            container=False,
        )
        send = gr.Button(
            "Send", variant="primary", scale=1, elem_classes=["me-send"]
        )

    with gr.Row(elem_classes=["me-examples"]):
        gr.Examples(
            examples=[[q] for q in EXAMPLES],
            inputs=[msg],
            label="Try asking",
        )

    gr.HTML(FOOTER_HTML)

    msg.submit(respond, [msg, chatbot], [msg, chatbot])
    send.click(respond, [msg, chatbot], [msg, chatbot])


if __name__ == "__main__":
    demo.launch(theme=BRAND_THEME, css=BRAND_CSS)
