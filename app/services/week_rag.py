from __future__ import annotations

from typing import Any, Dict, List, Optional


def week_metadata_filter(max_week_index: Optional[int]) -> Optional[Dict[str, Any]]:
    """Disabled - allow searching all weeks regardless of session week."""
    # Original filter: {"week_index": {"$lte": int(max_week_index)}}
    # Disabled to allow RAG to search all course materials
    return None


def rank_week_boosted_results(
    results: List[Dict[str, Any]],
    session_week_index: Optional[int],
    older_week_score_margin: float = 0.08,
) -> List[Dict[str, Any]]:
    if not results or session_week_index is None:
        return results

    session_hits = []
    older_hits = []
    for row in results:
        meta = row.get("metadata") or {}
        wk = meta.get("week_index")
        try:
            wk_int = int(wk) if wk is not None else None
        except (TypeError, ValueError):
            wk_int = None
        if wk_int == session_week_index:
            session_hits.append(row)
        else:
            older_hits.append(row)

    if not session_hits:
        return results

    best_session = max(session_hits, key=lambda r: r.get("score", 0))
    best_session_score = best_session.get("score", 0)
    threshold = best_session_score - older_week_score_margin

    filtered_older = [r for r in older_hits if r.get("score", 0) >= threshold]
    merged = session_hits + filtered_older
    merged.sort(key=lambda r: r.get("score", 0), reverse=True)
    return merged


def sources_to_citations(
    sources: List[Dict[str, Any]],
    max_items: int = 5,
) -> List[Dict[str, Any]]:
    citations: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for src in sources:
        meta = src if "course_material_id" in src else (src.get("metadata") or {})
        mat_id = meta.get("course_material_id")
        if not mat_id or mat_id in seen:
            continue
        seen.add(str(mat_id))
        label = meta.get("original_filename") or meta.get("source") or src.get("source")
        page = meta.get("page") or src.get("page")
        citations.append(
            {
                "course_material_id": str(mat_id),
                "label": label,
                "page": int(page) if page is not None and str(page).isdigit() else page,
            }
        )
        if len(citations) >= max_items:
            break
    return citations
