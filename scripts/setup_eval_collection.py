"""Ingest evaluation corpus into Qdrant collection `course_eval`.

Uses section-aware chunking so each academic topic stays cohesive for retrieval metrics.
"""

from __future__ import annotations

import asyncio
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(50))

from app.services.vector_store import get_vector_store

CONTENT_PATH = Path("data/evaluation/course_eval_content.txt")
COLLECTION = "course_eval"
MAX_CHUNK = 1200


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split on --- and major title lines; return (section_title, body)."""
    parts = re.split(r"\n---\n", text)
    sections: list[tuple[str, str]] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.splitlines()
        title = lines[0].strip() if lines else "section"
        # Further split long parts on blank-line bordered headings (ALL CAPS / Title lines)
        blocks = re.split(r"\n(?=[A-Z][^\n]{0,80}\n)", part)
        if len(blocks) <= 1:
            sections.append((title, part))
            continue
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            b_lines = block.splitlines()
            b_title = b_lines[0].strip()[:80]
            sections.append((b_title, block))
    return sections


def chunk_section(title: str, body: str) -> list[str]:
    """Prefer whole section; split only if longer than MAX_CHUNK with overlap."""
    if len(body) <= MAX_CHUNK:
        return [f"{title}\n\n{body}" if not body.startswith(title) else body]
    chunks: list[str] = []
    start = 0
    overlap = 200
    while start < len(body):
        end = start + MAX_CHUNK
        piece = body[start:end].strip()
        if piece:
            header = f"{title}\n\n" if start == 0 or title.lower() not in piece[:80].lower() else ""
            chunks.append(header + piece)
        if end >= len(body):
            break
        start = end - overlap
    return chunks


async def main() -> None:
    text = CONTENT_PATH.read_text(encoding="utf-8")
    sections = _split_sections(text)
    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []
    for idx, (title, body) in enumerate(sections):
        for j, chunk in enumerate(chunk_section(title, body)):
            documents.append(chunk)
            metadatas.append(
                {
                    "source": "course_eval_content.txt",
                    "section": title,
                    "section_index": idx,
                    "chunk_index": j,
                    "document_id": f"course_eval_{idx}_{j}",
                }
            )
            ids.append(f"course_eval_{idx}_{j}")

    print(f"Ingesting {len(documents)} section-aware chunks into '{COLLECTION}'...")

    vs = get_vector_store()
    # Wipe prior points by recreating collection if possible
    try:
        if vs._client is None:
            await vs.initialize()
        existing = [c.name for c in vs._client.get_collections().collections]
        if COLLECTION in existing:
            vs._client.delete_collection(COLLECTION)
            print(f"Deleted existing collection '{COLLECTION}'")
    except Exception as exc:
        print(f"Collection reset skipped: {exc}")

    await vs.add_documents(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
        collection_name=COLLECTION,
    )
    print(f"Done. {len(documents)} chunks ingested into '{COLLECTION}'.")


if __name__ == "__main__":
    asyncio.run(main())
