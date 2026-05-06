"""sapmcp: MCP server for SAP RFC calls without PyRFC."""

from __future__ import annotations

__all__ = ["__version__", "_connector"]
__version__ = "0.1.0"


def _connector(destination: str | None = None):
    """Create a SAP RFC connector for the requested logical destination."""

    from .config import SapConnectionConfig
    from .sap_rfc import SapRFCConnector

    return SapRFCConnector(SapConnectionConfig.from_destination(destination))
