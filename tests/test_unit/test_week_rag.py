from app.services.week_rag import (
    rank_week_boosted_results,
    sources_to_citations,
    week_metadata_filter,
)


def test_week_metadata_filter_none_when_unset():
    assert week_metadata_filter(None) is None


def test_week_metadata_filter_lte():
    # Product decision: week filter disabled so RAG can search all course materials.
    f = week_metadata_filter(3)
    assert f is None


def test_rank_week_boosted_drops_weak_older_week():
    session = 2
    results = [
        {"score": 0.9, "metadata": {"week_index": 2}},
        {"score": 0.5, "metadata": {"week_index": 1}},
        {"score": 0.85, "metadata": {"week_index": 1}},
    ]
    ranked = rank_week_boosted_results(results, session, older_week_score_margin=0.08)
    ids = [r["score"] for r in ranked]
    assert 0.9 in ids
    assert 0.85 in ids
    assert 0.5 not in ids


def test_rank_week_boosted_no_session_returns_original():
    results = [{"score": 1.0, "metadata": {"week_index": 5}}]
    assert rank_week_boosted_results(results, None) == results


def test_sources_to_citations_dedupes_by_material_id():
    sources = [
        {
            "metadata": {
                "course_material_id": "a",
                "original_filename": "One.pdf",
                "page": 1,
            }
        },
        {
            "metadata": {
                "course_material_id": "a",
                "original_filename": "One.pdf",
                "page": 2,
            }
        },
        {"metadata": {"course_material_id": "b", "source": "Two"}},
    ]
    cites = sources_to_citations(sources, max_items=5)
    assert len(cites) == 2
    assert cites[0]["course_material_id"] == "a"
