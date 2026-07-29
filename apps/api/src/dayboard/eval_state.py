from __future__ import annotations

import httpx


MAX_RESET_PAGES = 100


async def _cancel_active_items(
    client: httpx.AsyncClient,
    *,
    collection_path: str,
    params: dict[str, str | int],
) -> int:
    cancelled = 0
    cursor: str | None = None
    for _ in range(MAX_RESET_PAGES):
        request_params = {**params, **({"cursor": cursor} if cursor else {})}
        response = await client.get(collection_path, params=request_params)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError(f"Eval reset received invalid items from {collection_path}")

        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"Eval reset received an invalid item from {collection_path}")
            item_id = item.get("id")
            row_version = item.get("row_version")
            if not isinstance(item_id, str) or not isinstance(row_version, int):
                raise ValueError(f"Eval reset received an invalid item revision from {collection_path}")
            mutation = await client.post(
                f"{collection_path}/{item_id}/cancel",
                json={"expected_row_version": row_version},
            )
            mutation.raise_for_status()
            cancelled += 1

        cursor = payload.get("next_cursor")
        if not isinstance(cursor, str) or not cursor:
            return cancelled

    raise ValueError(f"Eval reset exceeded {MAX_RESET_PAGES} pages for {collection_path}")


async def reset_active_schedule(client: httpx.AsyncClient) -> dict[str, bool | int]:
    calendar_entries = await _cancel_active_items(
        client,
        collection_path="/api/calendar-entries",
        params={"status": "scheduled", "limit": 100},
    )
    task_items = await _cancel_active_items(
        client,
        collection_path="/api/task-items",
        params={"status": "open", "due_kind": "all", "limit": 100},
    )
    return {
        "performed": True,
        "calendar_entries_cancelled": calendar_entries,
        "task_items_cancelled": task_items,
    }
