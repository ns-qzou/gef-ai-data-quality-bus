"""Embedding configuration for ChromaDB.

Uses ChromaDB's built-in ONNX MiniLM-L6-v2 embedding function (no external downloads
needed once cached).
"""

from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2


def get_embedding_function() -> ONNXMiniLM_L6_V2:
    """Get ChromaDB's built-in ONNX embedding function.

    Returns:
        ONNXMiniLM_L6_V2 instance (384-dimensional embeddings).
    """
    return ONNXMiniLM_L6_V2()
