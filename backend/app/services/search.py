"""Semantic search service using ChromaDB."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

from app.config import get_config

logger = logging.getLogger(__name__)

# Timeout for ChromaDB operations (seconds)
CHROMA_TIMEOUT = 30


class SearchService:
    """
    Semantic search and similarity detection using ChromaDB.

    Uses ChromaDB's default embedding function (all-MiniLM-L6-v2)
    for generating embeddings from insight text.
    """

    def __init__(self):
        self._client: Optional[chromadb.ClientAPI] = None
        self._collection = None

    def _get_client(self) -> chromadb.ClientAPI:
        """Get or create ChromaDB client."""
        if self._client is None:
            # Store ChromaDB data alongside SQLite
            data_dir = Path(__file__).parent.parent.parent.parent / "data" / "chroma"
            data_dir.mkdir(parents=True, exist_ok=True)

            self._client = chromadb.PersistentClient(
                path=str(data_dir),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                ),
            )
            logger.info(f"ChromaDB initialized at {data_dir}")

        return self._client

    def _get_collection(self):
        """Get or create the insights collection."""
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name="insights",
                metadata={"description": "RedditWatch insight embeddings"},
            )
            logger.info(f"ChromaDB collection 'insights' has {self._collection.count()} documents")

        return self._collection

    def add_insight(
        self,
        insight_id: int,
        text: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Add an insight to the vector store.

        Args:
            insight_id: Database ID of the insight
            text: Text to embed (typically title + description + quote)
            metadata: Additional metadata to store
        """
        collection = self._get_collection()

        # Use insight_id as document ID
        doc_id = f"insight_{insight_id}"

        # Default metadata
        meta = metadata or {}
        meta["insight_id"] = insight_id

        collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[meta],
        )

    def add_insights_batch(
        self,
        insights: list[dict],
    ) -> int:
        """
        Add multiple insights to the vector store.

        Args:
            insights: List of dicts with id, text, and optional metadata

        Returns:
            Number of insights added
        """
        if not insights:
            return 0

        collection = self._get_collection()

        ids = [f"insight_{i['id']}" for i in insights]
        documents = [i["text"] for i in insights]
        metadatas = [
            {
                "insight_id": i["id"],
                "type": i.get("type", ""),
                "theme_key": i.get("theme_key", ""),
                "intensity_score": i.get("intensity_score", 0),
                "post_id": i.get("post_id", ""),
                "subreddit": i.get("subreddit", ""),
            }
            for i in insights
        ]

        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(f"Added {len(insights)} insights to ChromaDB")
        return len(insights)

    def _search_sync(
        self,
        query: str,
        limit: int,
        type_filter: Optional[str],
        theme_filter: Optional[str],
        min_intensity: Optional[int],
        subreddits: Optional[list[str]] = None,
    ) -> list[dict]:
        """Synchronous search implementation."""
        collection = self._get_collection()

        # Build where clause for filtering
        where = None
        where_conditions = []

        if type_filter:
            where_conditions.append({"type": {"$eq": type_filter}})
        if theme_filter:
            where_conditions.append({"theme_key": {"$eq": theme_filter}})
        if min_intensity is not None:
            where_conditions.append({"intensity_score": {"$gte": min_intensity}})
        if subreddits:
            where_conditions.append({"subreddit": {"$in": subreddits}})

        if len(where_conditions) == 1:
            where = where_conditions[0]
        elif len(where_conditions) > 1:
            where = {"$and": where_conditions}

        # Query the collection
        results = collection.query(
            query_texts=[query],
            n_results=limit,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        # Format results
        formatted = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                formatted.append({
                    "id": doc_id,
                    "insight_id": results["metadatas"][0][i].get("insight_id"),
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if results["distances"] else None,
                    "similarity": 1 - results["distances"][0][i] if results["distances"] else None,
                })

        return formatted

    def search(
        self,
        query: str,
        limit: int = 10,
        type_filter: Optional[str] = None,
        theme_filter: Optional[str] = None,
        min_intensity: Optional[int] = None,
        subreddits: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Semantic search for insights (sync).

        Args:
            query: Search query text
            limit: Maximum results to return
            type_filter: Filter by insight type
            theme_filter: Filter by theme_key
            min_intensity: Minimum intensity score
            subreddits: Filter to these subreddits only

        Returns:
            List of matching insights with scores
        """
        return self._search_sync(query, limit, type_filter, theme_filter, min_intensity, subreddits)

    async def search_async(
        self,
        query: str,
        limit: int = 10,
        type_filter: Optional[str] = None,
        theme_filter: Optional[str] = None,
        min_intensity: Optional[int] = None,
        subreddits: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Semantic search with timeout protection.

        Runs ChromaDB query in a thread to avoid blocking the event loop,
        with a timeout to prevent indefinite hangs.
        """
        return await asyncio.wait_for(
            asyncio.to_thread(
                self._search_sync, query, limit, type_filter, theme_filter, min_intensity, subreddits
            ),
            timeout=CHROMA_TIMEOUT,
        )

    def find_similar(
        self,
        insight_id: int,
        limit: int = 5,
        threshold: float = 0.8,
    ) -> list[dict]:
        """
        Find insights similar to a given insight.

        Args:
            insight_id: ID of the insight to find similar ones for
            limit: Maximum number of similar insights
            threshold: Minimum similarity score (0-1)

        Returns:
            List of similar insights
        """
        collection = self._get_collection()
        doc_id = f"insight_{insight_id}"

        # Get the insight's embedding
        try:
            result = collection.get(
                ids=[doc_id],
                include=["documents"],
            )
            if not result["documents"]:
                return []

            document = result["documents"][0]
        except Exception:
            return []

        # Search for similar
        results = collection.query(
            query_texts=[document],
            n_results=limit + 1,  # +1 because the insight itself will be returned
            include=["documents", "metadatas", "distances"],
        )

        # Format and filter results
        formatted = []
        if results and results["ids"] and results["ids"][0]:
            for i, rid in enumerate(results["ids"][0]):
                # Skip the insight itself
                if rid == doc_id:
                    continue

                distance = results["distances"][0][i] if results["distances"] else 0
                similarity = 1 - distance

                # Apply threshold
                if similarity < threshold:
                    continue

                formatted.append({
                    "id": rid,
                    "insight_id": results["metadatas"][0][i].get("insight_id"),
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "similarity": similarity,
                })

        return formatted[:limit]

    def find_duplicates(
        self,
        threshold: float = 0.9,
        limit: int = 50,
    ) -> list[dict]:
        """
        Find potential duplicate insights.

        Args:
            threshold: Minimum similarity to consider duplicate
            limit: Maximum pairs to return

        Returns:
            List of duplicate pairs with similarity scores
        """
        collection = self._get_collection()

        # Get all insights
        all_data = collection.get(
            include=["documents", "metadatas"],
        )

        if not all_data["ids"]:
            return []

        duplicates = []
        seen_pairs = set()

        # Check each insight against others
        for i, doc_id in enumerate(all_data["ids"]):
            if len(duplicates) >= limit:
                break

            # Find similar
            results = collection.query(
                query_texts=[all_data["documents"][i]],
                n_results=5,
                include=["metadatas", "distances"],
            )

            if not results["ids"] or not results["ids"][0]:
                continue

            for j, similar_id in enumerate(results["ids"][0]):
                if similar_id == doc_id:
                    continue

                # Create sorted pair to avoid duplicates
                pair = tuple(sorted([doc_id, similar_id]))
                if pair in seen_pairs:
                    continue

                distance = results["distances"][0][j]
                similarity = 1 - distance

                if similarity >= threshold:
                    seen_pairs.add(pair)
                    duplicates.append({
                        "insight_1_id": all_data["metadatas"][i].get("insight_id"),
                        "insight_2_id": results["metadatas"][0][j].get("insight_id"),
                        "similarity": similarity,
                    })

        return duplicates

    def get_stats(self) -> dict:
        """Get ChromaDB collection statistics."""
        try:
            collection = self._get_collection()
            return {
                "indexed_count": collection.count(),
                "collection_name": "insights",
            }
        except Exception as e:
            return {
                "indexed_count": 0,
                "error": str(e),
            }

    def reindex_all(self, insights: list[dict]) -> dict:
        """
        Reindex all insights (clears and rebuilds).

        Args:
            insights: List of all insights to index

        Returns:
            Statistics about the reindex operation
        """
        client = self._get_client()

        # Delete and recreate collection
        try:
            client.delete_collection("insights")
        except Exception:
            pass

        self._collection = None  # Reset cached collection

        # Add all insights
        count = self.add_insights_batch(insights)

        return {
            "indexed_count": count,
            "status": "complete",
        }


# Global search service instance
_search_service: Optional[SearchService] = None


def get_search_service() -> SearchService:
    """Get the global search service."""
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service
