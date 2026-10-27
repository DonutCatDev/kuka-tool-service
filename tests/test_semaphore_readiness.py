from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.request import Request


SCRIPT = Path(__file__).parents[1] / "scripts" / "inspect_semaphore_preflight.py"
SPEC = importlib.util.spec_from_file_location("inspect_semaphore_preflight", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Response:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def repository(repository_id: int = 9) -> dict[str, object]:
    return {
        "id": repository_id,
        "name": "KUKA Tool Service",
        "git_url": MODULE.EXPECTED_REPOSITORY,
        "git_branch": "main",
        "ssh_key_id": MODULE.EXPECTED_REPOSITORY_KEY_ID,
    }


def template(template_id: int = 300) -> dict[str, object]:
    return {
        "id": template_id,
        "name": "KUKA Tool Service - read-only preflight",
        "repository_id": 9,
        "inventory_id": MODULE.EXPECTED_INVENTORY_ID,
        "environment_id": MODULE.EXPECTED_ENVIRONMENT_ID,
        "playbook": "ansible/preflight.yml",
        "app": "ansible",
    }


def exported_template(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "name": "KUKA Tool Service - read-only preflight",
        "repository": "KUKA Tool Service",
        "playbook": "ansible/preflight.yml",
        "arguments": "[]",
        "allow_override_args_in_task": False,
        "allow_override_branch_in_task": False,
    }
    value.update(overrides)
    return value


def responses(
    *,
    repositories: list[dict[str, object]] | None = None,
    templates: list[dict[str, object]] | None = None,
    exports: list[dict[str, object]] | None = None,
) -> list[object]:
    return [
        repositories if repositories is not None else [repository()],
        [{"id": MODULE.EXPECTED_INVENTORY_ID, "name": "Fleetlord"}],
        templates if templates is not None else [template()],
        {"templates": exports if exports is not None else [exported_template()]},
    ]


def test_readiness_inspection_is_get_only_and_accepts_guarded_template() -> None:
    requests: list[Request] = []
    payloads = iter(responses())

    def opener(request: Request, timeout: int) -> Response:
        assert timeout == 10
        assert request.get_method() == "GET"
        assert request.data is None
        requests.append(request)
        return Response(next(payloads))

    result = MODULE.inspect_readiness("secret", opener=opener)

    assert result["ready"] is True
    assert result["task_launched"] is False
    assert len(requests) == 4
    assert requests[-1].full_url.endswith("/api/project/1/backup")
    assert all(request.headers["Authorization"] == "Bearer secret" for request in requests)


def test_readiness_fails_closed_without_exact_repository_and_template() -> None:
    payloads = iter(
        responses(
            repositories=[
                {
                    "id": 2,
                    "name": "Other",
                    "git_url": "https://example.invalid/other.git",
                    "git_branch": "main",
                    "ssh_key_id": 2,
                }
            ],
            templates=[
                {
                    **template(),
                    "repository_id": 2,
                    "playbook": "playbooks/deploy-fleet-services.yml",
                }
            ],
            exports=[],
        )
    )

    result = MODULE.inspect_readiness(
        "secret", opener=lambda request, timeout: Response(next(payloads))
    )

    assert result["repository_registered"] is False
    assert result["preflight_templates"] == []
    assert result["ready"] is False
    assert result["task_launched"] is False


def test_readiness_rejects_task_or_branch_overrides() -> None:
    for override in (
        {"allow_override_args_in_task": True},
        {"allow_override_branch_in_task": True},
    ):
        payloads = iter(responses(exports=[exported_template(**override)]))
        result = MODULE.inspect_readiness(
            "secret", opener=lambda request, timeout: Response(next(payloads))
        )
        assert result["ready"] is False


def test_readiness_rejects_wrong_inventory_environment_or_arguments() -> None:
    variants = (
        ({**template(), "inventory_id": 3}, exported_template()),
        ({**template(), "environment_id": 2}, exported_template()),
        (template(), exported_template(arguments='["--check"]')),
    )
    for candidate, exported in variants:
        payloads = iter(responses(templates=[candidate], exports=[exported]))
        result = MODULE.inspect_readiness(
            "secret", opener=lambda request, timeout: Response(next(payloads))
        )
        assert result["ready"] is False


def test_one_guarded_candidate_is_ready_when_an_obsolete_candidate_remains() -> None:
    obsolete = {**template(299), "name": "Obsolete preflight"}
    payloads = iter(
        responses(
            templates=[obsolete, template()],
            exports=[
                exported_template(
                    name="Obsolete preflight", allow_override_args_in_task=True
                ),
                exported_template(),
            ],
        )
    )

    result = MODULE.inspect_readiness(
        "secret", opener=lambda request, timeout: Response(next(payloads))
    )

    assert result["ready"] is True
