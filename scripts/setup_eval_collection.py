import sys
import asyncio
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(50))

from app.services.vector_store import get_vector_store

CONTENT_PATH = Path("data/evaluation/course_eval_content.txt")
COLLECTION = "course_eval"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def chunk_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c.strip() for c in chunks if c.strip()]


async def main():
    text = CONTENT_PATH.read_text(encoding="utf-8")
    chunks = chunk_text(text)
    print(f"Ingesting {len(chunks)} chunks into '{COLLECTION}'...")

    vs = get_vector_store()
    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [{"source": "course_eval_content.txt", "chunk_index": i} for i in range(len(chunks))]

    await vs.add_documents(
        documents=chunks,
        metadatas=metadatas,
        ids=ids,
        collection_name=COLLECTION,
    )
    print(f"Done. {len(chunks)} chunks ingested into '{COLLECTION}'.")


if __name__ == "__main__":
    asyncio.run(main())
