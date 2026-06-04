from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class InsightGenerationResult:
    title: str
    summary: str
    recommended_actions: list[str]
    confidence_label: str


class GeminiResponseError(ValueError):
    """Raised when the Gemini API returns an unexpected response shape."""


class InsightGenerationProvider:
    def generate(self, payload: dict[str, Any]) -> InsightGenerationResult:
        raise NotImplementedError


class RuleBasedInsightGenerationProvider(InsightGenerationProvider):
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


class GeminiInsightGenerationProvider(InsightGenerationProvider):
    api_url_template = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{model}:generateContent"
    )

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(self, payload: dict[str, Any]) -> InsightGenerationResult:
        prompt = self._build_prompt(payload)
        response = httpx.post(
            self.api_url_template.format(model=self.model),
            params={"key": self.api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.2,
                },
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        raw_text = self._extract_text(response.json())
        data = self._parse_json_payload(raw_text)
        return InsightGenerationResult(
            title=str(data["title"]).strip(),
            summary=str(data["summary"]).strip(),
            recommended_actions=[
                str(action).strip() for action in data["recommended_actions"]
            ],
            confidence_label=str(data.get("confidence_label") or "GEMINI").strip(),
        )

    def _build_prompt(self, payload: dict[str, Any]) -> str:
        serialized_payload = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        return (
            "You generate concise parent-facing school insights.\n"
            "Use only the supplied school context.\n"
            "Do not mention system design, AI providers, rule engines, demos, "
            "confidence, or internal processing.\n"
            "Do not include medical advice, legal advice, or punishment.\n"
            "Return strict JSON with exactly these keys: "
            "title, summary, recommended_actions, confidence_label.\n"
            "The recommended_actions value must be an array of 2 or 3 short strings.\n"
            'Use "GEMINI" for confidence_label.\n'
            f"Payload: {serialized_payload}"
        )

    def _extract_text(self, response_data: dict[str, Any]) -> str:
        candidates = response_data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            msg = "Gemini response did not contain candidates."
            raise GeminiResponseError(msg)

        content = candidates[0].get("content", {})
        parts = content.get("parts")
        if not isinstance(parts, list):
            msg = "Gemini response content parts are missing."
            raise GeminiResponseError(msg)

        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return part["text"]

        msg = "Gemini response did not contain a text part."
        raise GeminiResponseError(msg)

    def _parse_json_payload(self, raw_text: str) -> dict[str, Any]:
        candidate_text = raw_text.strip()
        if candidate_text.startswith("```"):
            candidate_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate_text)
        data = json.loads(candidate_text)
        if not isinstance(data, dict):
            msg = "Gemini response JSON was not an object."
            raise GeminiResponseError(msg)
        return data


MockInsightGenerationProvider = RuleBasedInsightGenerationProvider
