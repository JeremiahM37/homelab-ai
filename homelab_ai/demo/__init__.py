"""Demo mode — boot homelab-ai against fake in-process services so people
can try every feature without configuring anything.

Used by `homelab-ai demo`. The fake services live in homelab_ai/demo/services.
"""
from .runner import build_demo_config, run_demo

__all__ = ["build_demo_config", "run_demo"]
