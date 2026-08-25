"""
FSD 2.5 — Translation business logic:
  1. Send extracted text + session language to Bedrock/Claude with the
     constrained system prompt (i18n.build_system_prompt).
  2. Model returns plain-language explanation + structured fields.
  3. Fallback: if a term can't be confidently mapped, must say so explicitly.
"""
import json
import os
import boto3

from .i18n import build_system_prompt

BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0"
)

_bedrock_client = None


def _client():
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client(
            "bedrock-runtime", region_name=os.environ.get("AWS_REGION", "ap-southeast-1")
        )
    return _bedrock_client


def translate(raw_text: str, session_language: str) -> dict:
    """
    Calls Bedrock (Claude) via the Anthropic Messages API shape and parses the
    strict-JSON response defined in the system prompt.

    Returns a dict with keys: translated_text, medicine_name, frequency_code,
    meal_relation, duration, term_uncertain.
    """
    system_prompt = build_system_prompt(session_language)

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 800,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": f"Here is the raw OCR text extracted from a printed pharmacy label:\n\n{raw_text}",
            }
        ],
    }

    response = _client().invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    payload = json.loads(response["body"].read())
    text_out = "".join(
        block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"
    ).strip()

    return _parse_model_json(text_out, raw_text, session_language)


def _parse_model_json(text_out: str, raw_text: str, session_language: str) -> dict:
    # Strip accidental markdown fences defensively, then parse.
    cleaned = text_out.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned

    try:
        parsed = json.loads(cleaned)
        return {
            "translated_text": parsed.get("translated_text", "").strip() or text_out,
            "medicine_name": parsed.get("medicine_name") or None,
            "frequency_code": _normalize_freq(parsed.get("frequency_code")),
            "meal_relation": _normalize_meal(parsed.get("meal_relation")),
            "duration": parsed.get("duration") or None,
            "term_uncertain": bool(parsed.get("term_uncertain", False)),
        }
    except (json.JSONDecodeError, AttributeError):
        # FSD fallback rule: never silently omit or guess. If parsing itself
        # fails, surface the raw model text but flag it as uncertain rather
        # than fabricating structured fields.
        return {
            "translated_text": text_out or raw_text,
            "medicine_name": None,
            "frequency_code": None,
            "meal_relation": None,
            "duration": None,
            "term_uncertain": True,
        }


VALID_FREQUENCIES = {"OD", "OM", "ON", "BD", "TDS", "QID", "PRN"}


def _normalize_freq(value):
    if not value:
        return None
    value = str(value).strip().upper()
    return value if value in VALID_FREQUENCIES else None


def _normalize_meal(value):
    if not value:
        return None
    value = str(value).strip().upper()
    return value if value in {"AC", "PC"} else None
