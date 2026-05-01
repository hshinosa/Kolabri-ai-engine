from dataclasses import dataclass
from typing import List
import re


@dataclass
class PIIDetectionResult:
    has_pii: bool
    labels: List[str]
    masked_text: str


class PIIDetector:
    EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    PHONE = re.compile(r"\b(?:\+62|62|0)8[1-9][0-9]{7,10}\b")
    ID_NUMBER = re.compile(r"\b\d{16}\b")
    CREDIT_CARD = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")

    def detect(self, text: str) -> PIIDetectionResult:
        labels = []
        if self.EMAIL.search(text):
            labels.append("email")
        if self.PHONE.search(text):
            labels.append("phone")
        if self.ID_NUMBER.search(text):
            labels.append("id_number")
        if self.CREDIT_CARD.search(text):
            labels.append("credit_card")
        return PIIDetectionResult(has_pii=bool(labels), labels=labels, masked_text=self.mask(text))

    def mask(self, text: str) -> str:
        masked = self.EMAIL.sub("[EMAIL]", text)
        masked = self.PHONE.sub("[PHONE]", masked)
        masked = self.ID_NUMBER.sub("[ID_NUMBER]", masked)
        masked = self.CREDIT_CARD.sub("[CREDIT_CARD]", masked)
        return masked
