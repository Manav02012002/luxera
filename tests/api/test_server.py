from __future__ import annotations

import http.client
import json
import socketserver
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from luxera.api.server import LuxeraAPIHandler


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


@pytest.fixture()
def api_server():
    LuxeraAPIHandler._projects.clear()
    try:
        server = ThreadingTCPServer(("127.0.0.1", 0), LuxeraAPIHandler)
    except PermissionError:
        pytest.skip("Socket bind not permitted in current sandbox environment")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base = f"http://{host}:{port}"
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def _get_json(url: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return int(resp.status), json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return int(resp.status), json.loads(resp.read().decode("utf-8"))


def test_health_endpoint(api_server: str) -> None:
    status, body = _get_json(f"{api_server}/api/v1/health")
    assert status == 200
    assert body.get("status") == "ok"


def test_project_create(api_server: str) -> None:
    status, body = _post_json(
        f"{api_server}/api/v1/project/create",
        {"name": "api project", "rooms": [{"width": 6.0, "length": 8.0, "height": 3.0}]},
    )
    assert status == 200
    assert isinstance(body.get("project_id"), str)
    assert body.get("path")


def test_calc_run(api_server: str) -> None:
    _, created = _post_json(
        f"{api_server}/api/v1/project/create",
        {"name": "calc project", "rooms": [{"width": 6.0, "length": 8.0, "height": 3.0}]},
    )
    project_id = created["project_id"]

    _post_json(
        f"{api_server}/api/v1/luminaire/array",
        {"project_id": project_id, "asset_id": "default_asset", "rows": 2, "cols": 2, "height": 2.8},
    )
    status, body = _post_json(
        f"{api_server}/api/v1/calc/run",
        {"project_id": project_id, "job_type": "direct", "backend": "cpu"},
    )

    assert status == 200
    assert body.get("job_id")
    summary = body.get("summary", {})
    assert float(summary.get("E_avg", 0.0)) > 0.0


def test_library_search(api_server: str) -> None:
    url = f"{api_server}/api/v1/library/search?" + urllib.parse.urlencode({"query": "test"})
    status, body = _get_json(url)
    assert status == 200
    assert "results" in body
    assert "total" in body
    assert isinstance(body["results"], list)
    assert isinstance(body["total"], int)


def test_invalid_endpoint(api_server: str) -> None:
    req = urllib.request.Request(f"{api_server}/api/v1/nonexistent", method="GET")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=20)
    assert e.value.code == 404


def test_malformed_json(api_server: str) -> None:
    parsed = urllib.parse.urlparse(api_server)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=20)
    try:
        conn.request(
            "POST",
            "/api/v1/project/create",
            body="{not-valid-json",
            headers={"Content-Type": "application/json", "Content-Length": str(len("{not-valid-json"))},
        )
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 400
        assert body.get("error") == "bad_request"
    finally:
        conn.close()
