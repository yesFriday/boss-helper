"""JSON envelope formatter — stdout always structured JSON."""

import json
import sys
from typing import Optional


def ok(command: str, data=None, **kwargs) -> dict:
    envelope = {
        "ok": True,
        "command": command,
        "data": data,
        "error": None,
    }
    envelope.update(kwargs)
    return envelope


def fail(command: str, error: str) -> dict:
    return {
        "ok": False,
        "command": command,
        "data": None,
        "error": error,
    }


def emit(result: dict):
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def ok_or_fail(resp, command: str) -> dict:
    """Converts an httpx response to envelope. Handles HTTP errors."""
    if resp.is_error:
        return fail(command, f"HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        body = resp.json()
    except Exception:
        return fail(command, f"invalid JSON: {resp.text[:200]}")
    if isinstance(body, dict) and body.get("detail"):
        return fail(command, str(body["detail"]))
    return ok(command, data=body)
