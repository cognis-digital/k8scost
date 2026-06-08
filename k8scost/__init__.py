"""k8scost — part of the Cognis Neural Suite."""
try:  # re-export the tool's public API + identity from core
    from k8scost.core import *  # noqa: F401,F403
except Exception:  # pragma: no cover
    pass
try:
    from k8scost.core import TOOL_NAME, TOOL_VERSION
except Exception:  # pragma: no cover
    TOOL_NAME = "k8scost"
    TOOL_VERSION = "0.1.0"
__version__ = TOOL_VERSION
