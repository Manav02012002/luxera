from __future__ import annotations

import json
import socketserver
import threading
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


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return int(resp.status), json.loads(resp.read().decode("utf-8"))


def test_api_create_calc_report(api_server: str) -> None:
    status_create, created = _post_json(
        f"{api_server}/api/v1/project/create",
        {"name": "Integration API", "rooms": [{"width": 8.0, "length": 6.0, "height": 3.0}]},
    )
    assert status_create == 200
    project_id = str(created["project_id"])

    status_array, arr = _post_json(
        f"{api_server}/api/v1/luminaire/array",
        {"project_id": project_id, "rows": 2, "cols": 3, "height": 2.8, "asset_id": "default_asset"},
    )
    assert status_array == 200
    assert int(arr.get("count", 0)) == 6

    status_calc, calc = _post_json(
        f"{api_server}/api/v1/calc/run",
        {"project_id": project_id, "job_type": "direct", "backend": "cpu"},
    )
    assert status_calc == 200
    assert float(calc.get("summary", {}).get("E_avg", 0.0)) > 0.0

    status_cmp, cmp_res = _post_json(
        f"{api_server}/api/v1/compliance/check",
        {"project_id": project_id, "standard": "EN 12464-1", "activity_type": "OFFICE_GENERAL"},
    )
    assert status_cmp == 200
    assert "overall_status" in cmp_res

    status_report, report = _post_json(
        f"{api_server}/api/v1/report/generate",
        {"project_id": project_id, "format": "pdf", "type": "professional"},
    )
    assert status_report == 200
    assert report.get("path")
