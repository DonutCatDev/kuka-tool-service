#!/usr/bin/env python3
"""Inspect Semaphore for a suitable KUKA Tool Service preflight template.

This client is deliberately GET-only.  It cannot create, update, or launch a
Semaphore task.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SEMAPHORE_URL = "http://fleetlord.local:3002"
PROJECT_ID = 1
EXPECTED_REPOSITORY = "https://github.com/DonutCatDev/kuka-tool-service.git"
EXPECTED_PLAYBOOK = "ansible/preflight.yml"


def read_token(path: Path) -> str:
    metadata = path.stat()
    if metadata.st_uid != os.getuid():
        raise PermissionError("token file must be owned by the current user")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise PermissionError("token file must not be accessible by group or other users")
    token = path.read_text(encoding="utf-8").strip()
    if not token or any(character.isspace() for character in token):
        raise ValueError("token file must contain exactly one non-whitespace token")
    return token


def get_json(path: str, token: str, *, opener: Any = urllib.request.urlopen) -> Any:
    request = urllib.request.Request(
        f"{SEMAPHORE_URL}{path}",
        method="GET",
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
    )
    with opener(request, timeout=10) as response:
        body = response.read()
    return json.loads(body) if body else None


def _items(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RuntimeError(f"Semaphore returned an invalid {label} response")
    return value


def inspect_readiness(
    token: str,
    *,
    project_id: int = PROJECT_ID,
    opener: Any = urllib.request.urlopen,
) -> dict[str, Any]:
    repositories = _items(
        get_json(f"/api/project/{project_id}/repositories", token, opener=opener),
        "repositories",
    )
    inventories = _items(
        get_json(f"/api/project/{project_id}/inventory", token, opener=opener),
        "inventories",
    )
    templates = _items(
        get_json(f"/api/project/{project_id}/templates", token, opener=opener),
        "templates",
    )

    repository_ids = {
        item.get("id")
        for item in repositories
        if str(item.get("git_url", "")).rstrip("/") == EXPECTED_REPOSITORY.rstrip("/")
    }
    inventory_ids = {item.get("id") for item in inventories}
    candidates = []
    for template in templates:
        if template.get("repository_id") not in repository_ids:
            continue
        if str(template.get("playbook", "")).lstrip("./") != EXPECTED_PLAYBOOK:
            continue
        candidates.append(
            {
                "id": template.get("id"),
                "name": template.get("name"),
                "inventory_id": template.get("inventory_id"),
                "inventory_exists": template.get("inventory_id") in inventory_ids,
                "app": template.get("app"),
                "arguments_override_disabled": template.get(
                    "allow_override_args_in_task"
                )
                is False,
            }
        )

    return {
        "project_id": project_id,
        "repository_registered": bool(repository_ids),
        "repository_ids": sorted(item for item in repository_ids if isinstance(item, int)),
        "preflight_templates": candidates,
        "ready": any(
            candidate["inventory_exists"]
            and candidate["arguments_override_disabled"]
            and candidate["app"] == "ansible"
            for candidate in candidates
        ),
        "task_launched": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GET-only inspection of KUKA Tool Service Semaphore readiness."
    )
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--project-id", type=int, default=PROJECT_ID)
    args = parser.parse_args()
    try:
        result = inspect_readiness(read_token(args.token_file), project_id=args.project_id)
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
