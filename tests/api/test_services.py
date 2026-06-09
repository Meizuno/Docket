import uuid

import httpx


async def test_register_then_get_service(client: httpx.AsyncClient) -> None:
    created = await client.post("/services", json={"name": "worker-1"})
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "online"
    assert body["busy"] is False

    fetched = await client.get(f"/services/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "worker-1"


async def test_get_missing_service_returns_404(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(f"/services/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_register_empty_name_returns_400(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/services", json={"name": "   "})
    assert response.status_code == 400


async def test_list_services(client: httpx.AsyncClient) -> None:
    await client.post("/services", json={"name": "a"})
    await client.post("/services", json={"name": "b"})
    response = await client.get("/services")
    assert response.status_code == 200
    assert {s["name"] for s in response.json()} == {"a", "b"}


async def test_claim_returns_task_and_marks_service_busy(
    client: httpx.AsyncClient,
) -> None:
    service = (await client.post("/services", json={"name": "w"})).json()
    task = (await client.post("/tasks", json={"name": "compute"})).json()

    claimed = await client.post(f"/services/{service['id']}/claim")
    assert claimed.status_code == 200
    body = claimed.json()
    assert body["id"] == task["id"]
    assert body["status"] == "running"

    fetched = (await client.get(f"/services/{service['id']}")).json()
    assert fetched["busy"] is True


async def test_claim_empty_queue_returns_null(
    client: httpx.AsyncClient,
) -> None:
    service = (await client.post("/services", json={"name": "w"})).json()
    claimed = await client.post(f"/services/{service['id']}/claim")
    assert claimed.status_code == 200
    assert claimed.json() is None
