import uuid

import httpx


async def test_submit_then_get_task(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/tasks", json={"name": "compute", "payload": {"x": 1}}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["payload"] == {"x": 1}

    fetched = await client.get(f"/tasks/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "compute"


async def test_get_missing_task_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/tasks/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_submit_empty_name_returns_400(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/tasks", json={"name": "   "})
    assert response.status_code == 400


async def test_list_pending_tasks(client: httpx.AsyncClient) -> None:
    await client.post("/tasks", json={"name": "a"})
    response = await client.get("/tasks/pending")
    assert response.status_code == 200
    assert [t["name"] for t in response.json()] == ["a"]


async def test_claim_then_complete_lifecycle(
    client: httpx.AsyncClient,
) -> None:
    service = (await client.post("/services", json={"name": "w"})).json()
    task = (await client.post("/tasks", json={"name": "compute"})).json()
    await client.post(f"/services/{service['id']}/claim")

    completed = await client.post(
        f"/tasks/{task['id']}/complete",
        json={"service_id": service["id"], "result": {"value": 42}},
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "succeeded"
    assert body["result"] == {"value": 42}

    freed = (await client.get(f"/services/{service['id']}")).json()
    assert freed["busy"] is False


async def test_claim_then_fail_lifecycle(client: httpx.AsyncClient) -> None:
    service = (await client.post("/services", json={"name": "w"})).json()
    task = (await client.post("/tasks", json={"name": "compute"})).json()
    await client.post(f"/services/{service['id']}/claim")

    failed = await client.post(
        f"/tasks/{task['id']}/fail",
        json={"service_id": service["id"], "error": "boom"},
    )
    assert failed.status_code == 200
    body = failed.json()
    assert body["status"] == "failed"
    assert body["error"] == "boom"

    freed = (await client.get(f"/services/{service['id']}")).json()
    assert freed["busy"] is False


async def test_complete_non_running_task_returns_400(
    client: httpx.AsyncClient,
) -> None:
    service = (await client.post("/services", json={"name": "w"})).json()
    task = (await client.post("/tasks", json={"name": "compute"})).json()
    # Not claimed -> still PENDING, cannot be completed.
    response = await client.post(
        f"/tasks/{task['id']}/complete",
        json={"service_id": service["id"]},
    )
    assert response.status_code == 400
