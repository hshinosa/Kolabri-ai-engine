"""Shared data models for document processing pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ProcessedChunk:
    """A processed text chunk ready for embedding."""

    text: str
    metadata: Dict[str, Any]
    chunk_id: str


@dataclass
class ProcessedDocument:
    """Result of processing a single document."""

    filename: str
    file_type: str
    chunks: List[ProcessedChunk]
    page_count: int
    image_count: int
    total_characters: int
    processing_time_ms: float
    success: bool
    error: Optional[str] = None
