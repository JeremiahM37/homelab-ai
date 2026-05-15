"""Tier-3: smart LLM with file-edit plan + backup + audit + caps.

Flow:
  1. Ask the smart model for a plan as JSON:
       {"files_to_edit": [{"path": ".../sonarr.yaml",
                           "new_content": "..."}],
        "rationale": "..."}
  2. Validate against caps (max_files, max_lines).
  3. Snapshot every file to be edited.
  4. Apply each file's `new_content` (full replacement — simplest semantics
     that survive whitespace edge cases).
  5. Audit-log the diff + backup id.
  6. Optional: re-run verify; on failure, restore from snapshot.

The model gets the rationale-only first; if it asks for read-context it
calls `read_file`. It never gets a "delete" tool. The dispatcher rejects
any plan whose `new_content` would push a file outside the allowed root.
"""
from __future__ import annotations

import difflib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp

from homelab_ai.llm import get_client, get_model

from .audit import AuditLog
from .backup import FileBackup

if TYPE_CHECKING:
    from homelab_ai.agent.modules import Finding
    from homelab_ai.config import Config

logger = logging.getLogger("homelab_ai.fixer.tier3")


SYSTEM_PROMPT = """You are a homelab engineer with file-edit access. A
Tier-1 rule fix and a Tier-2 small-LLM investigation have already failed
to resolve the reported failure. Propose the minimum file change needed.

Rules:
- You can only edit files under the configured edit_root (passed in the user message).
- Never push to git, never call external services, never delete files.
- Hard caps: ≤ {max_files} files, ≤ {max_lines} lines per fix. The dispatcher
  will reject plans that exceed these.
- Output ONLY valid JSON (no markdown fences):
    {
      "files_to_edit": [
        {"path": "...", "new_content": "...the entire new contents..."}
      ],
      "rationale": "one-paragraph explanation"
    }
- If you don't know what to change, return {"files_to_edit": [], "rationale": "..."}
  — the dispatcher will treat that as an escalation to a human.
"""

READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a file under the edit_root and return its contents (max 50KB).",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
}


class SmartFixer:
    def __init__(self, cfg: Config, http: aiohttp.ClientSession):
        self.cfg = cfg
        self.http = http
        self.backup = FileBackup(cfg.agent.fixer.backup_dir)
        self.audit = AuditLog(cfg.agent.fixer.audit_log)
        # The edit root scopes what the smart LLM is allowed to touch.
        # Pulled from cfg if set; otherwise the working directory.
        raw = cfg._raw.get("agent", {}).get("fixer", {})
        self.edit_root = Path(raw.get("edit_root") or ".").resolve()

    def _is_inside_root(self, path: str) -> bool:
        try:
            return Path(path).resolve().is_relative_to(self.edit_root)
        except (ValueError, OSError):
            return False

    async def attempt_fix(self, finding: Finding) -> dict:
        plan = await self._invoke_smart_llm(finding)
        if not plan:
            return {"ok": False, "detail": "no plan returned"}
        if not plan.get("files_to_edit"):
            return {"ok": False, "detail": f"escalated to human: {plan.get('rationale', '')[:200]}"}

        # Enforce caps and scope.
        f = self.cfg.agent.fixer
        if len(plan["files_to_edit"]) > f.max_files_changed_per_fix:
            return {"ok": False, "detail": "plan exceeds max_files_changed_per_fix"}

        total_changed = 0
        for entry in plan["files_to_edit"]:
            path = entry.get("path", "")
            if not self._is_inside_root(path):
                return {"ok": False, "detail": f"path {path!r} outside edit_root"}
            new_content = entry.get("new_content", "")
            old_content = Path(path).read_text() if Path(path).is_file() else ""
            diff_lines = list(difflib.unified_diff(
                old_content.splitlines(), new_content.splitlines(),
                fromfile=path, tofile=path, lineterm="",
            ))
            total_changed += sum(
                1 for ln in diff_lines
                if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))
            )
            entry["_diff_lines"] = diff_lines
            entry["_old_content"] = old_content

        if total_changed > f.max_lines_changed_per_fix:
            return {"ok": False, "detail": f"plan changes {total_changed} lines (cap {f.max_lines_changed_per_fix})"}

        # Snapshot, apply, audit.
        for entry in plan["files_to_edit"]:
            path = entry["path"]
            backup_id = None
            if entry["_old_content"]:
                try:
                    backup_id = self.backup.snapshot(path)
                except Exception as e:
                    logger.warning("snapshot %s failed: %s", path, e)
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(entry.get("new_content", ""))
            self.audit.record(
                action="file_edit",
                target=path,
                rationale=plan.get("rationale", ""),
                diff="\n".join(entry["_diff_lines"]),
                backup_id=backup_id,
                extra={"finding": finding.message[:200]},
            )

        return {"ok": True, "files_changed": len(plan["files_to_edit"]), "lines_changed": total_changed}

    async def _invoke_smart_llm(self, finding: Finding) -> dict | None:
        f = self.cfg.agent.fixer
        sys_prompt = SYSTEM_PROMPT.format(
            max_files=f.max_files_changed_per_fix,
            max_lines=f.max_lines_changed_per_fix,
        )
        client = get_client(self.cfg, self.http)
        smart_model = get_model(self.cfg, "smart")
        user_msg = (
            f"Failure: {finding.message}\n"
            f"Module: {finding.module}, Target: {finding.target}, Severity: {finding.severity.name}\n"
            f"Context: {json.dumps(finding.context, default=str)[:1000]}\n"
            f"edit_root: {self.edit_root}\n"
            "Inspect any file you need with `read_file`. Reply with the JSON plan when ready."
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ]
        for _ in range(5):
            try:
                resp = await client.chat(
                    smart_model,
                    messages,
                    tools=[READ_FILE_TOOL],
                    stream=False,
                )
            except aiohttp.ClientError as e:
                logger.warning("tier-3 LLM unreachable: %s", e)
                return None
            msg = resp.get("message", {})
            calls = msg.get("tool_calls") or []
            if calls:
                messages.append(msg)
                for call in calls:
                    fn = call.get("function") or {}
                    args = fn.get("arguments") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    result = self._read_file(args.get("path", ""))
                    messages.append({"role": "tool", "content": json.dumps(result, default=str)})
                continue
            text = (msg.get("content") or "").strip()
            return _parse_plan(text)
        return None

    def _read_file(self, path: str) -> dict:
        if not self._is_inside_root(path):
            return {"error": "path outside edit_root"}
        p = Path(path)
        if not p.is_file():
            return {"error": "not a regular file"}
        try:
            data = p.read_text()
            if len(data) > 50_000:
                return {"truncated": True, "content": data[:50_000]}
            return {"content": data}
        except Exception as e:
            return {"error": str(e)[:200]}


def _parse_plan(text: str) -> dict | None:
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
    s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None
