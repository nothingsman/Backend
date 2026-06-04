from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class InsightGenerationResult:
    title: str
    summary: str
    recommended_actions: list[str]
    confidence_label: str


class InsightGenerationProvider:
    def generate(self, payload: dict[str, Any]) -> InsightGenerationResult:
        raise NotImplementedError


class MockInsightGenerationProvider(InsightGenerationProvider):
    def generate(self, payload: dict[str, Any]) -> InsightGenerationResult:
        concern = payload.get(
            "concern_summary",
            "A school-related concern was detected.",
        )
        actions = payload.get("suggested_actions") or [
            "Check in with your child about this issue.",
            "Review recent schoolwork or attendance together.",
            "Contact the teacher if the issue continues.",
        ]
        category = str(payload.get("category", "school")).replace("_", " ").title()
        risk_band = str(payload.get("risk_band", "LOW")).title()
        return InsightGenerationResult(
            title=f"{category} update for your child",
            summary=f"{concern} This is a {risk_band.lower()} priority update.",
            recommended_actions=[str(action)[:120] for action in actions][:3],
            confidence_label="RULE_BASED",
        )
