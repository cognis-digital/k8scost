"""Core cost & rightsizing engine. Standard library only.

Units
-----
CPU is expressed in millicores (m). 1 vCPU = 1000m.
Memory is expressed in mebibytes (Mi). 1 Gi = 1024 Mi.

The engine accepts either:
  * A list of simplified workload objects:
        {"name":..., "namespace":..., "replicas":N,
         "containers":[{"name":..., "cpu_request":"250m", "cpu_limit":"500m",
                        "mem_request":"256Mi", "mem_limit":"512Mi",
                        "cpu_usage":"80m", "mem_usage":"180Mi"}]}
  * Raw kubectl output: {"items":[<Deployment/StatefulSet/Pod>...]} or a single
    such object. usage hints may be supplied via metrics-server style objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

HOURS_PER_MONTH = 730.0


class CostError(Exception):
    """Raised on malformed input."""


# ---------------------------------------------------------------------------
# Quantity parsing (Kubernetes resource.Quantity subset)
# ---------------------------------------------------------------------------
def parse_cpu(v: Any) -> float:
    """Return CPU in millicores."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v) * 1000.0
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        if s.endswith("m"):
            return float(s[:-1])
        if s.endswith("n"):  # nanocores
            return float(s[:-1]) / 1e6
        if s.endswith("u"):  # microcores
            return float(s[:-1]) / 1e3
        return float(s) * 1000.0
    except ValueError:
        raise CostError(f"invalid CPU quantity: {v!r}")


_MEM_MULT = {
    "Ki": 1024 ** 1, "Mi": 1024 ** 2, "Gi": 1024 ** 3, "Ti": 1024 ** 4,
    "K": 1000 ** 1, "M": 1000 ** 2, "G": 1000 ** 3, "T": 1000 ** 4,
}


def parse_mem(v: Any) -> float:
    """Return memory in mebibytes (Mi)."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v) / (1024 ** 2)
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        for suf in ("Ki", "Mi", "Gi", "Ti", "K", "M", "G", "T"):
            if s.endswith(suf):
                return float(s[: -len(suf)]) * _MEM_MULT[suf] / (1024 ** 2)
        # plain bytes
        return float(s) / (1024 ** 2)
    except ValueError:
        raise CostError(f"invalid memory quantity: {v!r}")


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------
@dataclass
class PriceSheet:
    """Resource prices. Defaults approximate on-demand Linux cloud pricing."""
    cpu_core_hour: float = 0.031   # $ per vCPU-hour
    mem_gib_hour: float = 0.004    # $ per GiB-hour

    def cost(self, cpu_m: float, mem_mi: float) -> float:
        """Monthly $ for the given millicores + mebibytes."""
        cpu_cost = (cpu_m / 1000.0) * self.cpu_core_hour * HOURS_PER_MONTH
        mem_cost = (mem_mi / 1024.0) * self.mem_gib_hour * HOURS_PER_MONTH
        return cpu_cost + mem_cost


DEFAULT_PRICES = PriceSheet()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Container:
    name: str
    cpu_request: float = 0.0   # millicores
    cpu_limit: float = 0.0
    mem_request: float = 0.0   # Mi
    mem_limit: float = 0.0
    cpu_usage: Optional[float] = None  # millicores observed (hint)
    mem_usage: Optional[float] = None  # Mi observed (hint)


@dataclass
class Workload:
    name: str
    namespace: str = "default"
    kind: str = "Deployment"
    replicas: int = 1
    containers: list[Container] = field(default_factory=list)

    def requested(self) -> tuple[float, float]:
        cpu = sum(c.cpu_request for c in self.containers)
        mem = sum(c.mem_request for c in self.containers)
        return cpu, mem


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _container_from_simple(c: dict) -> Container:
    def opt(key):
        return c.get(key)
    return Container(
        name=c.get("name", "container"),
        cpu_request=parse_cpu(c.get("cpu_request")),
        cpu_limit=parse_cpu(c.get("cpu_limit")),
        mem_request=parse_mem(c.get("mem_request")),
        mem_limit=parse_mem(c.get("mem_limit")),
        cpu_usage=parse_cpu(opt("cpu_usage")) if opt("cpu_usage") is not None else None,
        mem_usage=parse_mem(opt("mem_usage")) if opt("mem_usage") is not None else None,
    )


def _container_from_k8s(spec: dict) -> Container:
    res = spec.get("resources", {}) or {}
    req = res.get("requests", {}) or {}
    lim = res.get("limits", {}) or {}
    return Container(
        name=spec.get("name", "container"),
        cpu_request=parse_cpu(req.get("cpu")),
        cpu_limit=parse_cpu(lim.get("cpu")),
        mem_request=parse_mem(req.get("memory")),
        mem_limit=parse_mem(lim.get("memory")),
    )


def _workload_from_k8s(obj: dict) -> Optional[Workload]:
    kind = obj.get("kind", "")
    meta = obj.get("metadata", {}) or {}
    spec = obj.get("spec", {}) or {}
    if kind == "Pod":
        pod_spec = spec
        replicas = 1
    else:
        replicas = int(spec.get("replicas", 1) or 1)
        tmpl = spec.get("template", {}) or {}
        pod_spec = tmpl.get("spec", {}) or {}
    containers = [_container_from_k8s(c) for c in pod_spec.get("containers", []) or []]
    if not containers:
        return None
    return Workload(
        name=meta.get("name", "workload"),
        namespace=meta.get("namespace", "default"),
        kind=kind or "Deployment",
        replicas=replicas,
        containers=containers,
    )


def parse_workloads(data: Any) -> list[Workload]:
    """Accept simplified-list, kubectl single object, or kubectl List."""
    if isinstance(data, dict) and "items" in data and "workloads" not in data:
        items = data["items"]
    elif isinstance(data, dict) and "workloads" in data:
        items = data["workloads"]
    elif isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        items = data
    else:
        raise CostError("input must be a JSON object or array")

    if not isinstance(items, list):
        raise CostError("'workloads'/'items' must be a JSON array")

    out: list[Workload] = []
    for it in items:
        if not isinstance(it, dict):
            raise CostError("each workload must be a JSON object")
        if "kind" in it and "spec" in it:  # raw k8s
            w = _workload_from_k8s(it)
            if w:
                out.append(w)
        else:  # simplified
            containers = [_container_from_simple(c) for c in it.get("containers", []) or []]
            if not containers:
                raise CostError(f"workload {it.get('name','?')!r} has no containers")
            raw_replicas = it.get("replicas", 1)
            try:
                replicas = int(raw_replicas or 1)
            except (TypeError, ValueError):
                raise CostError(
                    f"workload {it.get('name','?')!r}: 'replicas' must be an integer, got {raw_replicas!r}"
                )
            out.append(Workload(
                name=it.get("name", "workload"),
                namespace=it.get("namespace", "default"),
                kind=it.get("kind", "Deployment"),
                replicas=replicas,
                containers=containers,
            ))
    if not out:
        raise CostError("no workloads with containers found in input")
    return out


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
# Headroom factor applied to observed usage to derive a safe recommended
# request (covers spikes). Memory gets a touch more because OOMKill is fatal.
CPU_HEADROOM = 1.25
MEM_HEADROOM = 1.30
# A request is "over-provisioned" if recommended < request * this ratio.
OVERPROV_RATIO = 0.7
# Flag missing-request risk and limit-as-request fallbacks.


def _round_cpu(m: float) -> float:
    """Round millicores up to a sane step (10m)."""
    import math
    return max(10.0, math.ceil(m / 10.0) * 10.0)


def _round_mem(mi: float) -> float:
    """Round Mi up to nearest 16Mi."""
    import math
    return max(16.0, math.ceil(mi / 16.0) * 16.0)


def _analyze_container(c: Container, prices: PriceSheet) -> dict:
    findings: list[str] = []
    cur_cpu, cur_mem = c.cpu_request, c.mem_request

    rec_cpu, rec_mem = cur_cpu, cur_mem
    if c.cpu_usage is not None:
        rec_cpu = _round_cpu(c.cpu_usage * CPU_HEADROOM)
    if c.mem_usage is not None:
        rec_mem = _round_mem(c.mem_usage * MEM_HEADROOM)

    # Missing requests are a scheduling/cost risk.
    if cur_cpu == 0:
        findings.append("missing CPU request (unbounded scheduling, no cost attribution)")
        if c.cpu_usage is not None:
            rec_cpu = _round_cpu(c.cpu_usage * CPU_HEADROOM)
    if cur_mem == 0:
        findings.append("missing memory request (OOM/eviction risk)")
        if c.mem_usage is not None:
            rec_mem = _round_mem(c.mem_usage * MEM_HEADROOM)

    # Over-provisioning vs observed usage.
    if c.cpu_usage is not None and cur_cpu > 0 and rec_cpu < cur_cpu * OVERPROV_RATIO:
        findings.append(
            f"CPU over-provisioned: request {cur_cpu:.0f}m vs used ~{c.cpu_usage:.0f}m"
        )
    if c.mem_usage is not None and cur_mem > 0 and rec_mem < cur_mem * OVERPROV_RATIO:
        findings.append(
            f"memory over-provisioned: request {cur_mem:.0f}Mi vs used ~{c.mem_usage:.0f}Mi"
        )

    # Under-provisioning: usage above request risks throttling/OOM.
    if c.cpu_usage is not None and cur_cpu > 0 and c.cpu_usage > cur_cpu:
        findings.append(
            f"CPU under-provisioned: used ~{c.cpu_usage:.0f}m exceeds request {cur_cpu:.0f}m (throttling)"
        )
    if c.mem_usage is not None and cur_mem > 0 and c.mem_usage > cur_mem:
        findings.append(
            f"memory under-provisioned: used ~{c.mem_usage:.0f}Mi exceeds request {cur_mem:.0f}Mi (OOM risk)"
        )

    # Limit hygiene.
    if c.cpu_limit and c.cpu_request and c.cpu_limit > c.cpu_request * 4:
        findings.append("CPU limit >4x request (bursty noisy-neighbor risk)")
    if c.mem_limit and c.mem_request and c.mem_limit != c.mem_request:
        findings.append("memory limit != request (set equal to guarantee QoS Guaranteed)")
    if c.mem_limit == 0 and c.mem_request:
        findings.append("no memory limit (node memory pressure risk)")

    cur_cost = prices.cost(cur_cpu, cur_mem)
    rec_cost = prices.cost(rec_cpu, rec_mem)
    return {
        "name": c.name,
        "current": {
            "cpu_request_m": round(cur_cpu, 1),
            "mem_request_mi": round(cur_mem, 1),
            "cpu_limit_m": round(c.cpu_limit, 1),
            "mem_limit_mi": round(c.mem_limit, 1),
        },
        "usage": {
            "cpu_m": round(c.cpu_usage, 1) if c.cpu_usage is not None else None,
            "mem_mi": round(c.mem_usage, 1) if c.mem_usage is not None else None,
        },
        "recommended": {
            "cpu_request_m": round(rec_cpu, 1),
            "mem_request_mi": round(rec_mem, 1),
        },
        "monthly_cost": round(cur_cost, 2),
        "recommended_monthly_cost": round(rec_cost, 2),
        "monthly_savings": round(cur_cost - rec_cost, 2),
        "findings": findings,
    }


def analyze(workloads: list[Workload], prices: PriceSheet = DEFAULT_PRICES) -> list[dict]:
    """Per-workload cost + rightsizing report (scaled by replicas)."""
    results = []
    for w in workloads:
        creports = [_analyze_container(c, prices) for c in w.containers]
        rep = max(1, w.replicas)
        cur = sum(c["monthly_cost"] for c in creports) * rep
        recm = sum(c["recommended_monthly_cost"] for c in creports) * rep
        results.append({
            "name": w.name,
            "namespace": w.namespace,
            "kind": w.kind,
            "replicas": rep,
            "containers": creports,
            "monthly_cost": round(cur, 2),
            "recommended_monthly_cost": round(recm, 2),
            "monthly_savings": round(cur - recm, 2),
            "findings_count": sum(len(c["findings"]) for c in creports),
        })
    return results


def summarize(reports: list[dict]) -> dict:
    total = sum(r["monthly_cost"] for r in reports)
    rec = sum(r["recommended_monthly_cost"] for r in reports)
    savings = total - rec
    return {
        "workloads": len(reports),
        "total_monthly_cost": round(total, 2),
        "recommended_monthly_cost": round(rec, 2),
        "potential_monthly_savings": round(savings, 2),
        "savings_pct": round((savings / total * 100.0) if total else 0.0, 1),
        "total_findings": sum(r["findings_count"] for r in reports),
    }
