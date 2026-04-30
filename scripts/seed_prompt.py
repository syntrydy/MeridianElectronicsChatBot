"""One-off: push the local SYSTEM_PROMPT to Langfuse as the production version.

Run after editing SYSTEM_PROMPT in agent/prompts.py:
    python -m scripts.seed_prompt

This creates a new version under name `meridian-system` and moves the
`production` label to it. Existing versions are kept (Langfuse keeps history).
"""

from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv
from langfuse import get_client

from agent.prompts import PROMPT_LABEL, PROMPT_NAME, SYSTEM_PROMPT

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
LOG = logging.getLogger("seed_prompt")


def main() -> int:
    load_dotenv()
    langfuse = get_client()
    if not langfuse.auth_check():
        LOG.error("Langfuse auth failed — check LANGFUSE_PUBLIC_KEY / SECRET_KEY / HOST")
        return 1

    prompt = langfuse.create_prompt(
        name=PROMPT_NAME,
        prompt=SYSTEM_PROMPT,
        labels=[PROMPT_LABEL],
        type="text",
        commit_message="seed from agent/prompts.py",
    )
    LOG.info("Seeded prompt %r as version %s with label %r", PROMPT_NAME, prompt.version, PROMPT_LABEL)
    langfuse.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
