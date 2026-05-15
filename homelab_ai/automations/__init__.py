"""HA-style automation rules: when a Finding matches a trigger, call a
named tool with templated args.

Off by default — opt in via:

  features:
    automations:
      enabled: true
      rules:
        - name: restart_unhealthy_service
          trigger:
            type: finding
            severity: ERROR
            module: service_health
          action:
            tool: <service>_health      # any AI-callable tool
            args: {}

When a rule fires, the action is executed (silently) and the result is
optionally pushed through the notifier. See homelab_ai/automations/engine.py
for the full schema.
"""
from .engine import AutomationEngine, Rule

__all__ = ["AutomationEngine", "Rule"]
