from dataclasses import dataclass
from typing import List, Tuple
import re


@dataclass
class InjectionScore:
    is_injection: bool
    score: float
    reasons: List[str]
    policy_labels: List[str]


class InjectionDetector:
    # Heuristic + model-ready rule bundles. The goal is to keep the detector
    # compatible with a later BERT/transformer classifier without changing the API.
    INJECTION_PATTERNS: List[Tuple[str, str]] = [
        (r"\babaikan\s+instruksi\s+sebelumnya\b", "override_previous_instructions"),
        (r"\bignore\s+previous\s+instructions\b", "override_previous_instructions"),
        (r"\bforget\s+(?:all|everything|the)\s+(?:previous\s+)?instructions?\b", "forget_instructions"),
        (r"\b(system|developer|admin)\s*[:=]\s*", "role_impersonation"),
        (r"\breveal\s+(?:the\s+)?system\s+prompt\b", "prompt_extraction"),
        (r"\breveal\s+(?:all|the)\s+secrets?\b", "secret_extraction"),
        (r"\bjailbreak\b", "jailbreak"),
        (r"\bdeveloper\s+message\b", "role_leakage"),
    ]

    def score(self, text: str) -> InjectionScore:
        lower = text.lower()
        reasons = []
        policy_labels = []
        score = 0.0

        for pattern, label in self.INJECTION_PATTERNS:
            if re.search(pattern, lower, re.IGNORECASE):
                score += 0.35
                reasons.append(label)
                policy_labels.append(label)

        # Combination rules that are strong signals of adversarial intent.
        combo_rules = [
            ("ignore", "instruction", "ignore_instruction_combo"),
            ("override", "security", "override_security_combo"),
            ("show", "prompt", "prompt_disclosure_combo"),
            ("tampilkan", "rahasia", "secret_request"),
        ]
        for a, b, label in combo_rules:
            if a in lower and b in lower:
                score += 0.35 if label == "secret_request" else 0.2
                reasons.append(label)
                policy_labels.append(label)

        # Direct role manipulation is a strong prior for injection.
        if re.search(r"\b(as\s+an\s+ai|as\s+system|pretend\s+to\s+be)\b", lower):
            score += 0.25
            reasons.append("role_manipulation")
            policy_labels.append("role_manipulation")

        score = min(score, 1.0)
        return InjectionScore(
            is_injection=score >= 0.7,
            score=score,
            reasons=reasons,
            policy_labels=policy_labels,
        )
