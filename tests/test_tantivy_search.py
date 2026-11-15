from pathlib import Path

import pytest

from app.core.tantivy_search import SearchOperation, TantivyUserIndex, UserSearchDocument


@pytest.mark.asyncio
async def test_tantivy_search_upsert_delete_and_persistence(tmp_path: Path) -> None:
    document: UserSearchDocument = {
        "id": "user-1",
        "full_name": "Ada Lovelace",
        "email_bidx": "email-index",
        "phone_bidx": "phone-index",
        "roles": ["viewer", "super_admin"],
        "is_active": True,
    }
    index = TantivyUserIndex(tmp_path)
    await index.rebuild([document])

    results = await index.search_users("Lovelace")
    assert results == [document]

    updated = {**document, "full_name": "Ada Byron"}
    upsert: SearchOperation = {
        "event_type": "UPSERT",
        "aggregate_id": "user-1",
        "search_index": "users_v1",
        "payload": updated,
    }
    await index.apply_events([upsert])
    assert await index.search_users("Lovelace") == []
    assert await index.search_users("Byron") == [updated]
    await index.aclose()

    reopened = TantivyUserIndex(tmp_path)
    try:
        assert await reopened.search_users("Byron") == [updated]
        delete: SearchOperation = {
            "event_type": "DELETE",
            "aggregate_id": "user-1",
            "search_index": "users_v1",
            "payload": {},
        }
        await reopened.apply_events([delete])
        assert await reopened.search_users("Byron") == []
    finally:
        await reopened.aclose()
