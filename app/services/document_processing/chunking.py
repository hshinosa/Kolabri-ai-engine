from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ChunkSpec:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_id: str = ""


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def create_chunks(
    text: str,
    document_id: str,
    filename: str,
    page_number: int,
    chunk_size: int,
    chunk_overlap: int,
    metadata: Optional[Dict[str, Any]] = None,
) -> List[ChunkSpec]:
    chunks: List[ChunkSpec] = []
    text = clean_text(text)
    if not text:
        return chunks

    base_meta = dict(metadata or {})

    if len(text) <= chunk_size:
        chunks.append(
            ChunkSpec(
                text=text,
                metadata={
                    **base_meta,
                    "document_id": document_id,
                    "source": filename,
                    "page": page_number,
                    "chunk_index": 0,
                    "chunk_count": 1,
                },
                chunk_id=f"{document_id}_p{page_number}_c0",
            )
        )
        return chunks

    start = 0
    chunk_index = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            for separator in ["\n\n", ". ", ".\n", "? ", "! ", "\n"]:
                last_sep = text.rfind(separator, start + chunk_size // 2, end)
                if last_sep > start:
                    end = last_sep + len(separator)
                    break

        chunk_text = text[start:end].strip()

        if chunk_text:
            chunks.append(
                ChunkSpec(
                    text=chunk_text,
                    metadata={
                        **base_meta,
                        "document_id": document_id,
                        "source": filename,
                        "page": page_number,
                        "chunk_index": chunk_index,
                        "char_start": start,
                        "char_end": end,
                    },
                    chunk_id=f"{document_id}_p{page_number}_c{chunk_index}",
                )
            )
            chunk_index += 1

        new_start = end - chunk_overlap
        if new_start <= start:
            start = end
        else:
            start = new_start

    for chunk in chunks:
        chunk.metadata["chunk_count"] = len(chunks)

    return chunks
