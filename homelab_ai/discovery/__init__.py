"""Service auto-discovery.

`discover(hosts, http)` probes well-known ports on each host and returns
a list of candidate service blocks suitable for `config.yaml`. Used by
`homelab-ai init` and the future web wizard.
"""
from .probe import KNOWN_SERVICES, discover, probe_one

__all__ = ["KNOWN_SERVICES", "discover", "probe_one"]
