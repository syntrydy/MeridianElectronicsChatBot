"""Test customer credentials for live MCP. Used by smoke tests + demo runs.

These are seeded fixtures on the order-mcp staging server, not real PII.
"""

RETURNING_CUSTOMERS: list[tuple[str, str]] = [
    ("donaldgarcia@example.net", "7912"),
    ("michellejames@example.com", "1520"),
    ("laurahenderson@example.org", "1488"),
    ("spenceamanda@example.org", "2535"),
    ("glee@example.net", "4582"),
    ("williamsthomas@example.net", "4811"),
    ("justin78@example.net", "9279"),
    ("jason31@example.com", "1434"),
    ("samuel81@example.com", "4257"),
    ("williamleon@example.net", "9928"),
]
