"""k8scost - Kubernetes cost & rightsizing advisor (no Prometheus dependency).

Works from plain Kubernetes resource specs (kubectl get ... -o json, or a
simplified workload JSON) plus an optional cloud price sheet. Computes per-
workload monthly cost, finds over/under-provisioned containers using request
vs. limit vs. observed-usage hints, and emits actionable rightsizing advice.
"""
from .core import (
    Workload,
    PriceSheet,
    DEFAULT_PRICES,
    parse_workloads,
    analyze,
    summarize,
)

TOOL_NAME = "k8scost"
TOOL_VERSION = "1.0.0"

__all__ = [
    "Workload",
    "PriceSheet",
    "DEFAULT_PRICES",
    "parse_workloads",
    "analyze",
    "summarize",
    "TOOL_NAME",
    "TOOL_VERSION",
]
