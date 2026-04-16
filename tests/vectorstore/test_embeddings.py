"""Tests for embedding configuration."""

import numpy as np

from src.vectorstore.embeddings import get_embedding_function


class TestGetEmbeddingFunction:
    def test_returns_callable(self):
        ef = get_embedding_function()
        assert callable(ef)

    def test_embedding_dimensionality(self):
        ef = get_embedding_function()
        result = ef(["test query"])
        assert len(result) == 1
        assert len(result[0]) == 384  # MiniLM-L6-v2 output dimension

    def test_semantic_similarity_user_variants(self):
        ef = get_embedding_function()
        embeddings = ef(["user name", "username", "tenant identifier"])
        a = np.array(embeddings[0])
        b = np.array(embeddings[1])
        c = np.array(embeddings[2])
        sim_ab = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        sim_ac = np.dot(a, c) / (np.linalg.norm(a) * np.linalg.norm(c))
        # "user name" should be more similar to "username" than to "tenant identifier"
        assert sim_ab > sim_ac
