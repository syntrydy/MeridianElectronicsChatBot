from datetime import timedelta

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from config import get_settings


async def load_mcp_tools() -> list[BaseTool]:
    settings = get_settings()
    client = MultiServerMCPClient(
        {
            "order-mcp": {
                "transport": "streamable_http",
                "url": settings.mcp_server_url,
                "timeout": timedelta(seconds=settings.mcp_request_timeout),
            }
        }
    )
    return await client.get_tools()
