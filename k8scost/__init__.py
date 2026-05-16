"""K8SCOST — Kubernetes cost and rightsizing advisor with no Prometheus dependency."""
from k8scost.core import scan, TOOL_NAME, TOOL_VERSION
__all__ = ["scan", "TOOL_NAME", "TOOL_VERSION"]
