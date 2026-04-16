"""ChromaDB vector store for proto schema fields."""

import logging
from pathlib import Path

import chromadb

from src.errors import DataAccessError
from src.proto_parser.models import FieldRecord
from src.vectorstore.embeddings import get_embedding_function

logger = logging.getLogger(__name__)

COLLECTION_NAME = "proto_fields"


class SchemaStore:
    """ChromaDB-backed vector store for proto field records."""

    def __init__(self, persist_dir: Path) -> None:
        try:
            self._client = chromadb.PersistentClient(path=str(persist_dir))
            self._ef = get_embedding_function()
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=self._ef,
            )
        except Exception as e:
            raise DataAccessError(
                code="CHROMADB_INIT_ERROR",
                message=f"Failed to initialize ChromaDB: {e}",
                context={"persist_dir": str(persist_dir)},
                cause=e,
            ) from e

    def add_fields(self, fields: list[FieldRecord]) -> int:
        """Upsert field records into the vector store.

        Returns:
            Number of fields added.
        """
        if not fields:
            return 0

        ids = []
        documents = []
        metadatas = []

        for f in fields:
            doc_id = f"{f.file_path}:{f.message_name}.{f.field_name}"
            doc_text = f"{f.field_name} ({f.field_type}) in {f.message_name} from {f.package}"
            if f.comment:
                doc_text += f" — {f.comment}"

            ids.append(doc_id)
            documents.append(doc_text)
            metadatas.append({
                "field_name": f.field_name,
                "field_type": f.field_type,
                "message_name": f.message_name,
                "package": f.package,
                "file_path": f.file_path,
                "label": f.label,
                "fqn": f.fully_qualified_name,
            })

        self._collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        return len(ids)

    def query_similar_fields(
        self, field_name: str, field_type: str | None = None, n_results: int = 10
    ) -> list[dict]:
        """Query for fields similar to the given field name.

        Returns:
            List of dicts with 'document', 'metadata', 'distance' keys.
        """
        query_text = field_name
        if field_type:
            query_text += f" ({field_type})"

        results = self._collection.query(query_texts=[query_text], n_results=n_results)

        output = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                output.append({
                    "id": doc_id,
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                })
        return output

    def query_by_concept(self, concept: str, n_results: int = 20) -> list[dict]:
        """Query for fields matching a semantic concept (e.g., 'user identity').

        Returns:
            List of dicts with 'document', 'metadata', 'distance' keys.
        """
        return self.query_similar_fields(concept, n_results=n_results)

    def get_all_fields(self) -> list[dict]:
        """Retrieve all field records from the store.

        Returns:
            List of metadata dicts for all stored fields.
        """
        result = self._collection.get()
        output = []
        if result["ids"]:
            for i, doc_id in enumerate(result["ids"]):
                output.append({
                    "id": doc_id,
                    "document": result["documents"][i] if result["documents"] else "",
                    "metadata": result["metadatas"][i] if result["metadatas"] else {},
                })
        return output

    def count(self) -> int:
        """Return the number of records in the store."""
        return self._collection.count()

    def clear(self) -> None:
        """Delete and recreate the collection."""
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self._ef,
        )
