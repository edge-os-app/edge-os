"""The public Hermes route set and the host-application route guard.

Pure tests: no database, network or Docker. The matcher is the one place that decides whether a request is one of the
six public Hermes paths. The guard admits those paths and the two operator health paths, and refuses everything else.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from edge_os_api.core.hermes_public_route import (
    ROUTES, PublicRouteGuard, is_near_miss, match,
)

INTAKE = "0b7f5f3a-0a8f-4f6a-9a6e-1a2b3c4d5e6f"


SIX = [
    ("GET", "/v1/interpreter", None),
    ("POST", "/v1/research/requests", None),
    ("GET", "/v1/research/requests", None),
    ("GET", f"/v1/research/requests/{INTAKE}", INTAKE),
    ("POST", f"/v1/research/requests/{INTAKE}/clarifications", INTAKE),
    ("POST", f"/v1/research/requests/{INTAKE}/interpretation-retries", INTAKE),
]


def test_the_route_table_has_exactly_the_six_public_paths() -> None:
    assert {(route.method, route.template) for route in ROUTES} == {
        (method, path.replace(INTAKE, "{intake_id}")) for method, path, _ in SIX
    }


@pytest.mark.parametrize("method,path,intake", SIX)
def test_the_canonical_paths_match(method: str, path: str, intake: str | None) -> None:
    found = match(method, path, path.encode("ascii"))
    assert found is not None
    assert (found.method, found.path, found.intake_id) == (method, path, intake)


@pytest.mark.parametrize("method,path,intake", SIX)
def test_the_wrong_method_does_not_match(method: str, path: str, intake: str | None) -> None:
    assert match("PUT", path, path.encode("ascii")) is None


@pytest.mark.parametrize("method,path", [
    ("GET", "/v1/interpreter"),
    ("POST", "/v1/research/requests"),
    ("GET", "/v1/research/requests"),
    ("GET", f"/v1/research/requests/{INTAKE}"),
    ("POST", f"/v1/research/requests/{INTAKE}/clarifications"),
    ("POST", f"/v1/research/requests/{INTAKE}/interpretation-retries"),
])
def test_a_trailing_slash_does_not_match_but_is_a_near_miss(method: str, path: str) -> None:
    variant = path + "/"
    assert match(method, variant, variant.encode("ascii")) is None
    assert is_near_miss(method, variant) is True


@pytest.mark.parametrize("method,path", [
    ("GET", "/v1/interpreter"),
    ("GET", "/v1/research/requests"),
    ("GET", f"/v1/research/requests/{INTAKE}"),
])
def test_a_percent_encoded_byte_does_not_match_but_is_a_near_miss(method: str, path: str) -> None:
    variant = path.replace("/v1/", "/v%31/", 1)
    decoded = variant.replace("%31", "1")
    assert match(method, decoded, variant.encode("ascii")) is None
    assert is_near_miss(method, decoded) is True


@pytest.mark.parametrize("method,path", [
    ("GET", "/v1//interpreter"),
    ("POST", "/v1//research/requests"),
    ("GET", f"/v1/research/requests//{INTAKE}"),
])
def test_a_double_slash_does_not_match_but_is_a_near_miss(method: str, path: str) -> None:
    assert match(method, path, path.encode("ascii")) is None
    assert is_near_miss(method, path) is True


@pytest.mark.parametrize("method,path", [
    ("POST", "/v1/research/requests/../requests"),
    ("GET", "/v1/research/requests/../requests/" + INTAKE),
])
def test_a_dot_segment_does_not_match_but_is_a_near_miss_when_it_normalizes_to_a_six_path(
        method: str, path: str) -> None:
    assert match(method, path, path.encode("ascii")) is None
    assert is_near_miss(method, path) is True


@pytest.mark.parametrize("method,path", [
    ("GET", "/v1/interpreter"),
    ("POST", "/v1/research/requests"),
    ("GET", "/v1/research/requests"),
    ("GET", f"/v1/research/requests/{INTAKE}"),
    ("POST", f"/v1/research/requests/{INTAKE}/clarifications"),
    ("POST", f"/v1/research/requests/{INTAKE}/interpretation-retries"),
])
def test_a_case_change_does_not_match(method: str, path: str) -> None:
    variant = path.replace("/v1/", "/V1/", 1)
    assert match(method, variant, variant.encode("ascii")) is None


def test_a_non_canonical_uuid_does_not_match() -> None:
    upper = INTAKE.upper()
    path = f"/v1/research/requests/{upper}"
    assert match("GET", path, path.encode("ascii")) is None
    assert is_near_miss("GET", path) is True
    path = "/v1/research/requests/not-a-uuid"
    assert match("GET", path, path.encode("ascii")) is None
    assert is_near_miss("GET", path) is True


def test_a_non_ascii_path_does_not_match() -> None:
    path = "/v1/research/requests/\u00e9"
    assert match("GET", path, path.encode("utf-8")) is None
    assert is_near_miss("GET", path) is True


@pytest.mark.parametrize("path", [
    "/v1/research/requests/" + INTAKE + "/investigations",
    "/v1/research/requests/" + INTAKE + "/investigation-proposal",
    "/v1/research/requests/" + INTAKE + "/history-investigations",
    "/v1/research/requests/" + INTAKE + "/nansen-reports",
    "/v1/research/requests/" + INTAKE + "/market-adoptions",
    "/v1/research/requests/" + INTAKE + "/effect-runs",
    "/v1/research/history-datasets",
    "/v1/me",
])
def test_other_research_paths_are_not_near_misses(path: str) -> None:
    assert match("GET", path, path.encode("ascii")) is None
    assert is_near_miss("GET", path) is False


async def _ok_app(scope, receive, send) -> None:
    await JSONResponse({"ok": True})(scope, receive, send)


def guarded_client() -> TestClient:
    return TestClient(PublicRouteGuard(_ok_app))


@pytest.mark.parametrize("method,path,intake", SIX)
def test_the_guard_admits_the_six_paths(method: str, path: str, intake: str | None) -> None:
    response = guarded_client().request(method, path)
    assert response.status_code == 200 and response.json() == {"ok": True}


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_the_guard_admits_the_operator_health_paths(path: str) -> None:
    assert guarded_client().get(path).status_code == 200


def test_the_guard_admits_options_for_the_six() -> None:
    response = guarded_client().options("/v1/research/requests", headers={
        "Origin": "https://app.edgeos.fun", "Access-Control-Request-Method": "POST"})
    assert response.status_code == 200


@pytest.mark.parametrize("method,path", [
    ("GET", "/v1/interpreter/"),
    ("GET", "/v1/research/requests/"),
    ("GET", "/v1/research/requests/" + INTAKE + "/investigations"),
    ("GET", "/v1/research/requests/" + INTAKE + "/investigation-proposal"),
    ("GET", "/v1/me"),
    ("GET", "/openapi.json"),
    ("POST", "/v1/interpreter"),
])
def test_the_guard_refuses_everything_else_with_the_contract_envelope(method: str, path: str) -> None:
    response = guarded_client().request(method, path)
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found" and body["stage"] == "READ"


def test_the_guard_refuses_an_encoded_path() -> None:
    response = guarded_client().get("/v1/interpreter%2F")
    assert response.status_code == 404


def test_the_guard_refuses_a_dot_segment_path() -> None:
    response = guarded_client().get("/v1/research/requests/%2e%2e")
    assert response.status_code == 404


def test_the_route_identifier_is_a_uuid() -> None:
    found = match("GET", f"/v1/research/requests/{INTAKE}", f"/v1/research/requests/{INTAKE}".encode())
    assert found is not None and uuid.UUID(found.intake_id) == uuid.UUID(INTAKE)
