from dataclasses import dataclass
from typing import List


@dataclass
class ToxicityResult:
    is_toxic: bool
    score: float
    labels: List[str]


class ToxicityScorer:
    threshold = 0.2

    TOXIC_TERMS = {
        "bodoh": 0.25,
        "goblok": 0.35,
        "tolol": 0.35,
        "idiot": 0.3,
        "stupid": 0.25,
        "moron": 0.3,
        "fuck": 0.4,
        "shit": 0.3,
        "anjing": 0.3,
    }

    def score(self, text: str) -> ToxicityResult:
        lower = text.lower()
        labels = []
        score = 0.0
        for term, weight in self.TOXIC_TERMS.items():
            if term in lower:
                score += weight
                labels.append(term)
        score = min(score, 1.0)
        return ToxicityResult(is_toxic=score >= self.threshold, score=score, labels=labels)
