"""The 'brain': turns the spoken marking scheme into a rubric, then grades each
submission against it using Sarvam's vision + text models."""
from __future__ import annotations

import json
import re
from typing import Any

import config
from sarvam_client import chat

RUBRIC_SYSTEM = """You are an exam-grading assistant for a university course.
The teaching assistant has dictated, in speech, (a) general instructions and (b) a marking scheme.
The speech may be Hindi, English or a Hindi-English mix, and may be messy or repetitive.
Convert it into ONE strict JSON object. Do not write anything outside the JSON.

JSON shape:
{
  "title": "<short assignment title if mentioned, else ''>",
  "total_marks": <number>,
  "criteria": [
    {"id": "c1", "description": "<what is being checked>", "marks": <number>,
     "guidance": "<how marks are earned or lost>"}
  ],
  "penalties": [{"description": "<e.g. -0.5 for missing units>", "marks": <number>}],
  "feedback_style": "<how the TA wants the comment written>",
  "extra_instructions": "<anything else the TA said>",
  "assumptions": ["<anything you had to guess>"]
}
Rules: the criteria marks must add up to total_marks. If the scheme is ambiguous, make a sensible
assumption and list it under 'assumptions'. Keep descriptions short and concrete."""

GRADE_SYSTEM = """You are grading a student's HANDWRITTEN submission for a university course.
You receive the marking scheme as JSON and one or more photos/pages of the student's work.

Steps:
1. Read the handwriting carefully (it is often a rough phone photo of a notebook). Note the
   student's name / roll number if visible.
2. For EACH rubric criterion decide the marks awarded and give a one-sentence reason.
3. Total the marks. Every deduction must be explained.
4. Write a short, polite, student-facing comment stating the score and explaining exactly why
   any marks were deducted. This comment is posted privately to the student.

Return ONE strict JSON object, nothing outside it:
{
  "student": "<name if visible else ''>",
  "score": <number>,
  "max": <number>,
  "criteria": [{"id": "c1", "awarded": <number>, "max": <number>, "comment": "<why>"}],
  "deductions": ["<short reason>", ...],
  "feedback": "<the private comment for the student>",
  "confidence": "high|medium|low",
  "notes": "<anything a human must check, e.g. unreadable parts>"
}
Be fair and consistent. If a page is unreadable, say so in 'notes' and set confidence to 'low'
rather than guessing marks."""


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start:end + 1])
    raise ValueError(f"Model did not return JSON. Got: {text[:300]}")


def _image_parts(images_b64: list[str]) -> list[dict[str, Any]]:
    return [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        for b64 in images_b64
    ]


def parse_rubric(transcript: str, max_marks: float | None = None) -> dict[str, Any]:
    prompt = f"Here is the spoken marking scheme and instructions:\n\n\"\"\"\n{transcript}\n\"\"\""
    if max_marks is not None:
        prompt += f"\n\nThe assignment is out of {max_marks} marks in total."
    out = chat(
        [{"role": "system", "content": RUBRIC_SYSTEM}, {"role": "user", "content": prompt}],
        model=config.TEXT_MODEL, temperature=0.1,
    )
    rubric = _extract_json(out)
    if max_marks is not None:
        rubric.setdefault("total_marks", max_marks)
    return rubric


def grade_submission(images_b64: list[str], rubric: dict[str, Any],
                     extra_instructions: str = "") -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": "Marking scheme (JSON):\n" + json.dumps(rubric, ensure_ascii=False, indent=2)}
    ]
    if extra_instructions:
        content.append({"type": "text", "text": "Extra instructions from the TA: " + extra_instructions})
    content.append({"type": "text", "text": f"Student submission, {len(images_b64)} page(s):"})
    content.extend(_image_parts(images_b64))
    out = chat(
        [{"role": "system", "content": GRADE_SYSTEM}, {"role": "user", "content": content}],
        model=config.VISION_MODEL, temperature=0.1, max_tokens=3000,
    )
    return _extract_json(out)


def rewrite_feedback(text: str, language: str) -> str:
    """Re-write the student-facing comment in the requested language (e.g. Hindi)."""
    out = chat(
        [
            {"role": "system",
             "content": "Rewrite the following student feedback in the requested language. Keep it "
                        "short, warm and precise. Return only the rewritten text."},
            {"role": "user", "content": f"Language: {language}\n\n{text}"},
        ],
        model=config.TEXT_MODEL, temperature=0.2,
    )
    return out.strip()
