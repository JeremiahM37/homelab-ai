"""Built-in agent modules. Drop a new file here (or in ~/.config/homelab-ai/agent_modules/)
to add a scan."""
from .base import AgentModule, Finding, Severity

__all__ = ["AgentModule", "Finding", "Severity"]
