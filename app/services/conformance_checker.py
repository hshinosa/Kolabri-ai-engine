from dataclasses import dataclass
from typing import List, Dict, Tuple


@dataclass
class ConformanceResult:
    is_conformant: bool
    alignment_score: float
    missing_activities: List[str]
    extra_activities: List[str]
    token_replay_score: float
    alignment_details: List[str]


class ConformanceChecker:
    EXPECTED_SEQUENCE = ["GOAL_SETTING", "STUDENT_MESSAGE", "BOT_RESPONSE", "REFLECTION_SUBMITTED"]

    def check(self, observed_sequence: List[str]) -> ConformanceResult:
        missing = [x for x in self.EXPECTED_SEQUENCE if x not in observed_sequence]
        extra = [x for x in observed_sequence if x not in self.EXPECTED_SEQUENCE]

        # Alignment-style score: reward expected transitions in order.
        ordered_hits = 0
        details: List[str] = []
        expected_index = 0
        for event in observed_sequence:
            if expected_index < len(self.EXPECTED_SEQUENCE) and event == self.EXPECTED_SEQUENCE[expected_index]:
                ordered_hits += 1
                details.append(f"matched:{event}")
                expected_index += 1
            elif event in self.EXPECTED_SEQUENCE:
                # Late or out-of-order but still expected.
                details.append(f"out_of_order:{event}")
            else:
                details.append(f"unexpected:{event}")

        coverage_score = ordered_hits / max(len(self.EXPECTED_SEQUENCE), 1)
        penalty = (len(extra) * 0.05) + (len(missing) * 0.1)
        alignment_score = max(0.0, min(1.0, coverage_score - penalty + 0.1))

        # Token replay-style score: how much of the normative path can be replayed.
        token_replay_score = max(0.0, min(1.0, coverage_score - (len(extra) * 0.05)))

        return ConformanceResult(
            is_conformant=alignment_score >= 0.8 and not missing,
            alignment_score=round(alignment_score, 3),
            missing_activities=missing,
            extra_activities=extra,
            token_replay_score=round(token_replay_score, 3),
            alignment_details=details,
        )
