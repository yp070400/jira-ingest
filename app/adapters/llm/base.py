"""Re-export LLMPort and EmbeddingPort for adapter convenience imports."""
from app.domain.interfaces.llm_port import LLMPort, QuickAnalysisResult, DeepAnalysisResult
from app.domain.interfaces.embedding_port import EmbeddingPort

__all__ = ["LLMPort", "EmbeddingPort", "QuickAnalysisResult", "DeepAnalysisResult"]
