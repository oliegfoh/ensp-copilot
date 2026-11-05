"""ensp-copilot: auditable local automation for Huawei eNSP labs.

Zero third-party runtime dependencies. Requires Python 3.10+ and a running
eNSP instance on the same Windows host.
"""
__version__ = "0.1.0"

from .topo import Device, Link, Topology, parse_topo, classify_model

__all__ = ["Device", "Link", "Topology", "parse_topo", "classify_model", "__version__"]
