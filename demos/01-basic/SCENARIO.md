# Demo: rightsizing an over-provisioned namespace

A small team runs three Deployments. They sized requests by guessing and
never revisited them. They have no Prometheus, but they grabbed a one-off
`kubectl top pods` snapshot and pasted observed usage into the workload file.

`workloads.json` describes the three Deployments with their requests, limits,
and observed (`*_usage`) CPU/memory.

## What to expect

- **api** (3 replicas): requests 500m / 512Mi but only uses ~80m / 180Mi —
  badly over-provisioned. k8scost recommends ~100m / 240Mi.
- **worker** (2 replicas): uses *more* memory than it requests — flagged as
  an OOM risk (under-provisioned).
- **cache** (1 replica): no memory limit set — flagged as a node-pressure risk.

## Run it

```bash
# Human-readable table with detailed advice
python -m k8scost analyze demos/01-basic/workloads.json --advise

# Machine-readable JSON (pipe to jq, store in CI artifacts, etc.)
python -m k8scost --format json analyze demos/01-basic/workloads.json

# Use your own cloud price sheet
python -m k8scost --cpu-price 0.04 --mem-price 0.005 analyze demos/01-basic/workloads.json
```

The `summary.potential_monthly_savings` field is the headline number: the
estimated monthly dollars freed by adopting the recommended requests.
