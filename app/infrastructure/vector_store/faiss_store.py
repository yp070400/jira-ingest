"""FAISS vector store implementation with on-disk persistence."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path

import faiss
import numpy as np

from app.config import get_settings
from app.domain.interfaces.vector_store_port import SearchResult, VectorStorePort

logger = logging.getLogger(__name__)

_INDEX_FILE = "jira_intel.index"
_MAPPING_FILE = "jira_intel_mapping.json"
_DELETED_FILE = "jira_intel_deleted.json"


class FAISSVectorStore(VectorStorePort):
    """
    FAISS flat inner-product index with:
    - Cosine similarity (via L2 normalization)
    - Persistent on-disk storage
    - Soft-delete via deleted-ID tracking
    - Thread-safe async locking
    """

    def __init__(
        self,
        index_path: str | None = None,
        dimension: int | None = None,
    ) -> None:
        settings = get_settings()
        self._index_path = Path(index_path or settings.faiss_index_path)
        self._dimension = dimension or settings.faiss_index_dimension
        self._index: faiss.IndexIDMap | None = None
        self._id_to_ticket: dict[int, str] = {}   # faiss_id -> ticket_id
        self._ticket_to_id: dict[str, int] = {}   # ticket_id -> faiss_id
        self._deleted_ids: set[int] = set()
        self._next_id: int = 0
        self._lock = asyncio.Lock()
        self._dirty = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def load(self) -> None:
        """Load index and mappings from disk."""
        async with self._lock:
            self._index_path.mkdir(parents=True, exist_ok=True)
            index_file = self._index_path / _INDEX_FILE
            mapping_file = self._index_path / _MAPPING_FILE
            deleted_file = self._index_path / _DELETED_FILE

            if index_file.exists():
                self._index = faiss.read_index(str(index_file))
                logger.info(
                    "Loaded FAISS index with %d vectors from %s",
                    self._index.ntotal,
                    index_file,
                )
            else:
                self._index = self._create_new_index()
                logger.info("Created new FAISS index (dim=%d)", self._dimension)

            if mapping_file.exists():
                with open(mapping_file) as f:
                    raw = json.load(f)
                self._id_to_ticket = {int(k): v for k, v in raw.get("id_to_ticket", {}).items()}
                self._ticket_to_id = raw.get("ticket_to_id", {})
                self._next_id = raw.get("next_id", 0)
            else:
                self._id_to_ticket = {}
                self._ticket_to_id = {}
                self._next_id = 0

            if deleted_file.exists():
                with open(deleted_file) as f:
                    self._deleted_ids = set(json.load(f))
            else:
                self._deleted_ids = set()

    def _create_new_index(self) -> faiss.IndexIDMap:
        """Create a new normalized inner-product index."""
        flat = faiss.IndexFlatIP(self._dimension)
        index = faiss.IndexIDMap(flat)
        return index

    async def persist(self) -> None:
        """Flush index and mappings to disk."""
        async with self._lock:
            await self._persist_unsafe()

    async def _persist_unsafe(self) -> None:
        """Persist without acquiring the lock (caller holds it)."""
        self._index_path.mkdir(parents=True, exist_ok=True)
        index_file = self._index_path / _INDEX_FILE
        mapping_file = self._index_path / _MAPPING_FILE
        deleted_file = self._index_path / _DELETED_FILE

        faiss.write_index(self._index, str(index_file))

        with open(mapping_file, "w") as f:
            json.dump(
                {
                    "id_to_ticket": {str(k): v for k, v in self._id_to_ticket.items()},
                    "ticket_to_id": self._ticket_to_id,
                    "next_id": self._next_id,
                },
                f,
                indent=2,
            )

        with open(deleted_file, "w") as f:
            json.dump(list(self._deleted_ids), f)

        self._dirty = False
        logger.debug(
            "Persisted FAISS index: %d total, %d deleted", self._index.ntotal, len(self._deleted_ids)
        )

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def add_vector(self, ticket_id: str, vector: np.ndarray) -> int:
        """Add a normalized vector and return its FAISS ID."""
        normalized = self._normalize(vector)
        async with self._lock:
            if ticket_id in self._ticket_to_id:
                # Already exists — update instead
                existing_id = self._ticket_to_id[ticket_id]
                await self._update_unsafe(existing_id, normalized)
                return existing_id

            faiss_id = self._next_id
            self._next_id += 1

            ids = np.array([faiss_id], dtype=np.int64)
            vecs = normalized.reshape(1, -1).astype(np.float32)
            self._index.add_with_ids(vecs, ids)

            self._id_to_ticket[faiss_id] = ticket_id
            self._ticket_to_id[ticket_id] = faiss_id
            self._dirty = True

            if self._index.ntotal % 100 == 0:
                await self._persist_unsafe()

            return faiss_id

    async def update_vector(self, faiss_index_id: int, vector: np.ndarray) -> None:
        async with self._lock:
            await self._update_unsafe(faiss_index_id, self._normalize(vector))

    async def _update_unsafe(self, faiss_index_id: int, normalized: np.ndarray) -> None:
        """FAISS doesn't support in-place update; remove + re-add."""
        ids_to_remove = np.array([faiss_index_id], dtype=np.int64)
        self._index.remove_ids(ids_to_remove)
        vecs = normalized.reshape(1, -1).astype(np.float32)
        ids = np.array([faiss_index_id], dtype=np.int64)
        self._index.add_with_ids(vecs, ids)
        self._dirty = True

    async def delete_vector(self, faiss_index_id: int) -> None:
        async with self._lock:
            self._deleted_ids.add(faiss_index_id)
            ids_to_remove = np.array([faiss_index_id], dtype=np.int64)
            self._index.remove_ids(ids_to_remove)
            # Remove from mappings
            ticket_id = self._id_to_ticket.pop(faiss_index_id, None)
            if ticket_id:
                self._ticket_to_id.pop(ticket_id, None)
            self._dirty = True

    # ── Search ───────────────────────────────────────────────────────────────

    async def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        similarity_threshold: float = 0.0,
    ) -> list[SearchResult]:
        """Return top-k similar tickets above threshold."""
        if self._index is None or self._index.ntotal == 0:
            return []

        normalized = self._normalize(query_vector)
        query = normalized.reshape(1, -1).astype(np.float32)

        # Request more than top_k to account for deleted IDs
        k_actual = min(top_k * 3, self._index.ntotal)
        async with self._lock:
            distances, ids = self._index.search(query, k_actual)

        results: list[SearchResult] = []
        for distance, faiss_id in zip(distances[0], ids[0]):
            if faiss_id == -1:
                continue
            if faiss_id in self._deleted_ids:
                continue

            similarity = float(distance)  # inner product of normalized vectors = cosine sim
            similarity = max(0.0, min(1.0, similarity))  # clamp

            if similarity < similarity_threshold:
                continue

            ticket_id = self._id_to_ticket.get(int(faiss_id))
            if not ticket_id:
                continue

            results.append(
                SearchResult(
                    ticket_id=ticket_id,
                    faiss_index_id=int(faiss_id),
                    similarity_score=similarity,
                    distance=1.0 - similarity,
                )
            )
            if len(results) >= top_k:
                break

        return results

    # ── Reindex ──────────────────────────────────────────────────────────────

    async def rebuild_index(self, vectors: list[tuple[str, np.ndarray]]) -> None:
        """Atomically rebuild the index from a full vector set."""
        async with self._lock:
            self._index = self._create_new_index()
            self._id_to_ticket = {}
            self._ticket_to_id = {}
            self._deleted_ids = set()
            self._next_id = 0

            if not vectors:
                await self._persist_unsafe()
                return

            ticket_ids = []
            vecs_list = []
            for i, (ticket_id, vector) in enumerate(vectors):
                normalized = self._normalize(vector)
                ticket_ids.append(ticket_id)
                vecs_list.append(normalized)
                self._id_to_ticket[i] = ticket_id
                self._ticket_to_id[ticket_id] = i

            self._next_id = len(vectors)
            all_ids = np.arange(len(vectors), dtype=np.int64)
            all_vecs = np.stack(vecs_list, axis=0).astype(np.float32)
            self._index.add_with_ids(all_vecs, all_ids)

            await self._persist_unsafe()
            logger.info("Rebuilt FAISS index with %d vectors", len(vectors))

    # ── Utilities ────────────────────────────────────────────────────────────

    def count(self) -> int:
        if self._index is None:
            return 0
        return self._index.ntotal - len(self._deleted_ids)

    def has_ticket(self, ticket_id: str) -> bool:
        return ticket_id in self._ticket_to_id

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        vec = vector.astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm < 1e-10:
            return vec
        return vec / norm

    @staticmethod
    def compute_vector_hash(vector: np.ndarray) -> str:
        return hashlib.sha256(vector.tobytes()).hexdigest()
