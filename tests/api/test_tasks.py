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
