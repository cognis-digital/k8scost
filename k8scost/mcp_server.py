"""K8SCOST MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from k8scost.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-k8scost[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-k8scost[mcp]'")
        return 1
    app = FastMCP("k8scost")

    @app.tool()
    def k8scost_scan(target: str) -> str:
        """Kubernetes cost and rightsizing advisor with no Prometheus dependency. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
