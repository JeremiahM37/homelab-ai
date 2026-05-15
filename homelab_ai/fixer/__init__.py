"""3-tier auto-repair.

Tier 1 — rule-based (always safe, no LLM): restart container, retry indexer,
         re-trigger import, clear cache, etc.
Tier 2 — small LLM with a constrained tool catalog (restart_service,
         retry_job, fetch_logs). Can read but not write files.
Tier 3 — smart LLM that can edit files. Every edit is backed up to
         `backup_dir` before write, every action is appended to
         `audit_log.md`. Hard caps on files/lines changed per fix.
"""
from .audit import AuditLog
from .backup import FileBackup

__all__ = ["AuditLog", "FileBackup"]
