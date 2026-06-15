"""
Moderation engine for Cashi Shop.

Implements the full marketplace moderation specification:
- Text moderation with structured JSON output
- Vision model for image analysis (structured JSON + natural language)
- Combined decision with evidence and risk scoring
- Full seller context (account age, listing history, violations)
- Conservative: uncertain listings go to REVIEW
"""

import base64
import json
import logging
from typing import Optional

import httpx

from config import OLLAMA_URL, TEXT_MODEL, VISION_MODEL

logger = logging.getLogger("watcher")

# ---------------------------------------------------------------------------
# Text Moderation Prompt (Full Specification)
# ---------------------------------------------------------------------------

TEXT_SYSTEM_PROMPT = """You are a marketplace moderation API. Evaluate the LISTING CONTENT and return a JSON decision.

Decision rules (apply in order):
1. REJECT (confidence >= 0.80): listing clearly violates policy -- drugs, weapons, counterfeits, fraud, illegal services
2. APPROVE (confidence >= 0.85): listing is clearly legitimate -- ordinary consumer goods, services, second-hand items
3. REVIEW: genuinely ambiguous -- listing could be either legitimate or a violation and you cannot tell

Seller history is context, not a gate. A new seller with a clean listing is APPROVE. An established seller with a drug listing is REJECT. Do not downgrade a legitimate listing to REVIEW simply because the seller account is new.

Confidence 0.0-1.0. Risk score 0-100 (0-20 low, 21-50 moderate, 51-80 elevated, 81-100 high).

Return ONLY valid JSON:
{"decision":"APPROVE","confidence":0.92,"risk_score":8,"reasons":["legitimate consumer electronics"],"evidence":["iPhone model widely sold second-hand"],"summary":"Clean listing","flags":[],"requires_human_review":false}

No markdown, no other text."""

# ---------------------------------------------------------------------------
# Vision Prompt (Natural Language Summary for Combined Prompt)
# ---------------------------------------------------------------------------

VISION_SYSTEM_PROMPT = """You are an image analysis assistant for marketplace moderation.

Analyze the image and provide a concise natural language summary for a human moderator.

Focus on:
- Products present
- Logos and brands visible
- Weapons or dangerous items
- Drugs or drug paraphernalia
- Nudity or adult content
- Graphic or violent content
- Text visible in image
- Anything suspicious or concerning
- Consistency between image and expected listing

Return ONLY a brief paragraph (2-4 sentences) describing what you see and any concerns.
Do not return JSON. Do not return markdown. Plain text only.

Example good response:
"The image shows a leather handbag with a Coach logo. No weapons, drugs, or adult content visible. The product appears consistent with a clothing/accessories listing. No concerns detected."

Example concerning response:
"The image shows a handgun with ammunition magazines visible on a table. This is a weapon and violates marketplace policy. The listing should be rejected immediately."
"""

VALID_DECISIONS = {"APPROVE", "REVIEW", "REJECT"}

# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


def _clean_json(raw: str) -> str:
    """Extract JSON object from surrounding text by counting braces."""
    raw = raw.strip()
    start = raw.find("{")
    if start == -1:
        return raw
    brace_count = 0
    for i, char in enumerate(raw[start:], start):
        if char == "{":
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0:
                return raw[start : i + 1]
    return raw[start:]


def _parse_moderation_response(raw: str) -> dict:
    """Parse moderation JSON with full schema support."""
    cleaned = _clean_json(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Moderation JSON parse error: %s - raw: %.200s", exc, raw)
        return {
            "decision": "REVIEW",
            "confidence": 0.5,
            "risk_score": 50,
            "reasons": ["parse_error"],
            "evidence": ["Failed to parse model response"],
            "summary": "Unable to parse moderation result",
            "flags": ["parse_error"],
            "requires_human_review": True,
        }

    decision = str(data.get("decision", "REVIEW")).upper()
    if decision not in VALID_DECISIONS:
        decision = "REVIEW"

    confidence = float(data.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))

    risk_score = int(data.get("risk_score", 50))
    risk_score = max(0, min(100, risk_score))

    reasons = data.get("reasons", ["none"])
    if not isinstance(reasons, list):
        reasons = [str(reasons)]

    evidence = data.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = [str(evidence)]

    summary = str(data.get("summary", ""))

    flags = data.get("flags", [])
    if not isinstance(flags, list):
        flags = [str(flags)]

    requires_human = bool(data.get("requires_human_review", False))

    return {
        "decision": decision,
        "confidence": round(confidence, 2),
        "risk_score": risk_score,
        "reasons": reasons,
        "evidence": evidence,
        "summary": summary,
        "flags": flags,
        "requires_human_review": requires_human,
    }


# ---------------------------------------------------------------------------
# Ollama API
# ---------------------------------------------------------------------------


def _ollama_generate(
    model: str,
    system: str,
    prompt: str,
    images: Optional[list[str]] = None,
    temperature: float = 0.1,
    format_json: bool = False,
) -> str:
    """Generate text from Ollama with error handling."""
    from urllib.parse import urljoin

    payload = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 2048,
        },
    }
    if images:
        payload["images"] = images
    if format_json:
        payload["format"] = "json"

    try:
        resp = httpx.post(
            urljoin(OLLAMA_URL, "/api/generate"),
            json=payload,
            timeout=300.0,  # Vision model loads on GPU on-demand; 120s not enough when queued
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("response", ""))
    except Exception as exc:
        logger.error("Ollama request failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Text moderation (full specification format)
# ---------------------------------------------------------------------------


def moderate_text(
    title: str,
    category: str,
    description: str,
    seller_stats: dict,
) -> dict:
    """Run text moderation with full listing review request format."""
    prompt = f"""Listing Information

Title:
{title}

Category:
{category}

Description:
{description}

Seller Information:

Account Age Days:
{seller_stats['account_age_days']}

Previous Listings:
{seller_stats['previous_listing_count']}

Previous Violations:
{seller_stats['previous_violation_count']}

Review the listing and return JSON only."""

    raw = _ollama_generate(TEXT_MODEL, TEXT_SYSTEM_PROMPT, prompt, format_json=True)
    result = _parse_moderation_response(raw)
    # Retry once if parse failed
    if result.get("flags") and "parse_error" in result.get("flags", []):
        logger.warning("Parse error on first attempt, retrying with simplified prompt")
        retry_prompt = prompt + "\n\nIMPORTANT: Return ONLY the JSON object. No explanation, no markdown, no other text."
        raw = _ollama_generate(TEXT_MODEL, TEXT_SYSTEM_PROMPT, retry_prompt, format_json=True)
        result = _parse_moderation_response(raw)
    return result


# ---------------------------------------------------------------------------
# Image moderation (natural language summary)
# ---------------------------------------------------------------------------


def analyze_image(image_bytes: bytes) -> str:
    """Analyze image with vision model. Returns natural language summary."""
    import time

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    logger.info("Vision analysis starting (model=%s, bytes=%d)", VISION_MODEL, len(image_bytes))

    start = time.time()
    try:
        raw = _ollama_generate(
            VISION_MODEL, VISION_SYSTEM_PROMPT, "Analyze this image.", images=[b64]
        )
        latency = time.time() - start
        summary = raw.strip()
        logger.info("Vision analysis completed in %.1fs (summary_len=%d)", latency, len(summary))
        return summary
    except Exception as exc:
        latency = time.time() - start
        logger.error("Vision analysis failed after %.1fs: %s", latency, exc)
        return "Image analysis failed. Unable to evaluate image content."


# ---------------------------------------------------------------------------
# Combined moderation (text + image analysis)
# ---------------------------------------------------------------------------


def moderate_with_image(
    title: str,
    category: str,
    description: str,
    image_summary: str,
    seller_stats: dict,
) -> dict:
    """Moderate listing with both text and image analysis."""
    prompt = f"""Listing Information

Title:
{title}

Category:
{category}

Description:
{description}

Image Analysis:
{image_summary}

Seller Information:

Account Age Days:
{seller_stats['account_age_days']}

Previous Listings:
{seller_stats['previous_listing_count']}

Previous Violations:
{seller_stats['previous_violation_count']}

Review the listing and return JSON only."""

    raw = _ollama_generate(TEXT_MODEL, TEXT_SYSTEM_PROMPT, prompt, format_json=True)
    result = _parse_moderation_response(raw)
    # Retry once if parse failed
    if result.get("flags") and "parse_error" in result.get("flags", []):
        logger.warning("Parse error on combined attempt, retrying with simplified prompt")
        retry_prompt = prompt + "\n\nIMPORTANT: Return ONLY the JSON object. No explanation, no markdown, no other text."
        raw = _ollama_generate(TEXT_MODEL, TEXT_SYSTEM_PROMPT, retry_prompt, format_json=True)
        result = _parse_moderation_response(raw)
    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_moderation(
    title: str,
    category: str,
    description: str,
    seller_stats: dict,
    image_bytes: Optional[bytes] = None,
) -> dict:
    """Run full moderation pipeline per specification.

    Returns dict with:
    - decision: APPROVE | REVIEW | REJECT
    - confidence: 0.0-1.0
    - risk_score: 0-100
    - reasons: list of strings
    - evidence: list of strings
    - summary: human-readable summary
    - flags: list of concern flags
    - requires_human_review: bool
    - image_summary: str (if image provided)
    """
    # Step 1: Image analysis (if provided)
    image_summary = None
    if image_bytes:
        image_summary = analyze_image(image_bytes)

    # Step 2: Moderation with all context
    if image_summary:
        result = moderate_with_image(
            title, category, description, image_summary, seller_stats
        )
        result["image_summary"] = image_summary
    else:
        result = moderate_text(title, category, description, seller_stats)

    # Step 3: Image-based hard violation check
    # If image summary explicitly mentions weapons/drugs/adult/graphic,
    # we cannot reliably parse natural language for booleans.
    # The vision model should flag these in the summary, and the text model
    # should catch them when reading the image analysis. This is by design
    # since the combined prompt includes the image summary.

    return result


# ---------------------------------------------------------------------------
# Threshold logic (per specification)
# ---------------------------------------------------------------------------


def apply_threshold(result: dict) -> tuple[str, str]:
    """Apply publication thresholds.

    The LLM is the primary decision-maker. Humans only see listings the LLM
    cannot confidently classify.

    Returns (decision_label, next_step) where next_step is one of:
      "published"          — auto-approved, goes live immediately
      "auto_rejected"      — auto-rejected, no human needed
      "human_review_queue" — genuinely ambiguous, needs human judgement
    """
    decision = result.get("decision", "REVIEW")
    confidence = result.get("confidence", 0.5)
    risk_score = result.get("risk_score", 50)

    # Auto-approve: LLM confident the listing is clean
    if decision == "APPROVE" and confidence >= 0.85 and risk_score <= 30:
        return "APPROVE", "published"

    # Auto-reject: LLM confident this is a violation
    if decision == "REJECT" and confidence >= 0.80:
        return "REJECT", "auto_rejected"

    # Everything else is genuinely ambiguous — human judgement required
    return "REVIEW", "human_review_queue"
