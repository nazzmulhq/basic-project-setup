import asyncio
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, TypedDict

import tantivy
from fastapi import Depends

from app.core.config import settings
from app.models.user import User


class UserSearchDocument(TypedDict):
    id: str
    full_name: str
    email_bidx: str
    phone_bidx: str
    roles: list[str]
    is_active: bool


class SearchOperation(TypedDict):
    event_type: str
    aggregate_id: str
    search_index: str
    payload: Mapping[str, Any]


def user_search_document(user: User) -> UserSearchDocument:
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "email_bidx": user.email_bidx,
        "phone_bidx": user.phone_bidx,
        "roles": user.role_names,
        "is_active": user.is_active,
    }


class TantivyUserIndex:
    def __init__(self, path: str | Path) -> None:
        index_path = Path(path)
        index_path.mkdir(parents=True, exist_ok=True)

        schema_builder = tantivy.SchemaBuilder()
        schema_builder.add_text_field("id", stored=True, tokenizer_name="raw")
        schema_builder.add_text_field("full_name", stored=True)
        schema_builder.add_text_field("email_bidx", stored=True, tokenizer_name="raw")
        schema_builder.add_text_field("phone_bidx", stored=True, tokenizer_name="raw")
        schema_builder.add_text_field("roles", stored=True, tokenizer_name="raw")
        schema_builder.add_boolean_field("is_active", stored=True)

        self.index = tantivy.Index(schema_builder.build(), path=str(index_path), reuse=True)
        self.writer = self.index.writer(heap_size=15_000_000, num_threads=1)
        self._lock = threading.Lock()
        self._closed = False

    async def is_empty(self) -> bool:
        return await asyncio.to_thread(self._is_empty)

    def _is_empty(self) -> bool:
        with self._lock:
            self._ensure_open()
            return self.index.searcher().num_docs == 0

    async def rebuild(self, documents: Sequence[UserSearchDocument]) -> None:
        await asyncio.to_thread(self._rebuild, documents)

    def _rebuild(self, documents: Sequence[UserSearchDocument]) -> None:
        with self._lock:
            self._ensure_open()
            try:
                self.writer.delete_all_documents()
                for values in documents:
                    self.writer.add_document(self._make_document(values))
                self.writer.commit()
                self.index.reload()
            except Exception:
                self.writer.rollback()
                raise

    async def apply_events(self, operations: Sequence[SearchOperation]) -> None:
        await asyncio.to_thread(self._apply_events, operations)

    def _apply_events(self, operations: Sequence[SearchOperation]) -> None:
        if not operations:
            return
        with self._lock:
            self._ensure_open()
            try:
                for operation in operations:
                    if operation["search_index"] != "users_v1":
                        raise ValueError(
                            f"Unsupported Tantivy search index: {operation['search_index']}"
                        )
                    self.writer.delete_documents_by_term("id", operation["aggregate_id"])
                    if operation["event_type"] == "UPSERT":
                        self.writer.add_document(self._make_document(operation["payload"]))
                    elif operation["event_type"] != "DELETE":
                        raise ValueError(f"Unsupported search event: {operation['event_type']}")
                self.writer.commit()
                self.index.reload()
            except Exception:
                self.writer.rollback()
                raise

    async def search_users(self, query: str, limit: int = 10) -> list[dict[str, object]]:
        return await asyncio.to_thread(self._search_users, query, limit)

    def _search_users(self, query: str, limit: int) -> list[dict[str, object]]:
        with self._lock:
            self._ensure_open()
            parsed_query = self.index.parse_query(
                query,
                ["full_name"],
                fuzzy_fields={"full_name": (True, 1, True)},
            )
            searcher = self.index.searcher()
            result = searcher.search(parsed_query, limit=limit)
            documents = []
            for _, address in result.hits:
                document = searcher.doc(address)
                documents.append(
                    {
                        "id": document["id"][0],
                        "full_name": document["full_name"][0],
                        "email_bidx": document["email_bidx"][0],
                        "phone_bidx": document["phone_bidx"][0],
                        "roles": document["roles"],
                        "is_active": document["is_active"][0],
                    }
                )
            return documents

    async def aclose(self) -> None:
        await asyncio.to_thread(self._close)

    def _close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self.writer.commit()
            self.writer.wait_merging_threads()
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Tantivy user index is closed")

    @staticmethod
    def _make_document(values: Mapping[str, Any]) -> tantivy.Document:
        document = tantivy.Document()
        document.add_text("id", str(values["id"]))
        document.add_text("full_name", str(values["full_name"]))
        document.add_text("email_bidx", str(values["email_bidx"]))
        document.add_text("phone_bidx", str(values["phone_bidx"]))
        for role in values["roles"]:
            document.add_text("roles", str(role))
        document.add_boolean("is_active", bool(values["is_active"]))
        return document


tantivy_user_index: TantivyUserIndex | None = None


def init_tantivy_user_index() -> TantivyUserIndex:
    global tantivy_user_index
    if tantivy_user_index is not None:
        raise RuntimeError("Tantivy user index has already been initialized")
    tantivy_user_index = TantivyUserIndex(settings.search_index_path)
    return tantivy_user_index


async def close_tantivy_user_index() -> None:
    global tantivy_user_index
    if tantivy_user_index is not None:
        index = tantivy_user_index
        try:
            await index.aclose()
        finally:
            tantivy_user_index = None


def get_tantivy_user_index() -> TantivyUserIndex:
    if tantivy_user_index is None:
        raise RuntimeError("Tantivy user index has not been initialized")
    return tantivy_user_index


TantivyUserIndexDeps = Annotated[TantivyUserIndex, Depends(get_tantivy_user_index)]
