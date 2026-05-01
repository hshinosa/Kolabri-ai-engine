from app.services.rag import RAGPipeline


class TestRAGTokenBehavior:
    def test_multi_source_context_construction(self):
        pipeline = RAGPipeline.__new__(RAGPipeline)

        docs = [
            {"content": "OOP is a paradigm based on objects.", "metadata": {"source": "ch1.pdf", "page": 1}},
            {"content": "Inheritance allows code reuse between classes.", "metadata": {"source": "ch3.pdf", "page": 5}},
            {"content": "Polymorphism enables flexible interfaces.", "metadata": {"source": "ch5.pdf", "page": 12}},
        ]

        context = pipeline._build_multi_source_context(docs)

        assert "ch1.pdf" in context
        assert "ch3.pdf" in context
        assert "[Sumber 1" in context

    def test_prompt_encourages_multi_hop(self):
        pipeline = RAGPipeline.__new__(RAGPipeline)

        docs = [
            {"content": "Definition of X", "metadata": {"source": "a.pdf"}},
            {"content": "Example of X in practice", "metadata": {"source": "b.pdf"}},
        ]

        prompt = pipeline._build_rag_token_prompt(
            query="Jelaskan X dan berikan contoh",
            context_docs=docs,
        )

        assert "sumber" in prompt.lower() or "source" in prompt.lower() or "dokumen" in prompt.lower()
