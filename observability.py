import logging
from functools import lru_cache

from langfuse import get_client
from langfuse.langchain import CallbackHandler

LOG = logging.getLogger(__name__)


@lru_cache
def get_langfuse_handler() -> CallbackHandler:
    if not get_client().auth_check():
        LOG.warning(
            "Langfuse auth check failed — traces will not appear. "
            "Verify LANGFUSE_PUBLIC_KEY / SECRET_KEY / HOST."
        )
    else:
        LOG.info("Langfuse auth OK")
    return CallbackHandler()
