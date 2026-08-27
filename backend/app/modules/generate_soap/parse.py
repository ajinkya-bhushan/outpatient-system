"""Split Aava SOAP markdown into Subjective / Objective / Assessment / Plan."""

from __future__ import annotations

import re

SECTION_ORDER = ("subjective", "objective", "assessment", "plan")

# Aava gold sample uses "## S – SUBJECTIVE". Also accept hashes-off labels,
# ASCII hyphens, em-dashes, and a bare section name.
_HEADING = re.compile(
    r"^#{0,3}\s*"
    r"(?:\*{0,2})?"
    r"(?:([SOAP])\s*[–—\-:]\s*)?"
    r"(SUBJECTIVE|OBJECTIVE|ASSESSMENT|PLAN)"
    r"\b.*$",
    re.IGNORECASE | re.MULTILINE,
)

_TITLES = {
    "subjective": "## S – SUBJECTIVE",
    "objective": "## O – OBJECTIVE",
    "assessment": "## A – ASSESSMENT",
    "plan": "## P – PLAN",
}


def _empty_sections() -> dict[str, str]:
    return {name: "" for name in SECTION_ORDER}


def parse_soap_markdown(markdown: str) -> dict[str, str]:
    """Return four SOAP sections. Missing headings yield empty strings.

    Text before the first heading is prepended to Subjective. If no heading is
    found, the whole document becomes Subjective.
    """
    sections = _empty_sections()
    text = markdown or ""
    matches = list(_HEADING.finditer(text))
    if not matches:
        sections["subjective"] = text.strip()
        return sections

    preamble = text[: matches[0].start()].strip()
    for index, match in enumerate(matches):
        name = match.group(2).lower()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            existing = sections[name]
            sections[name] = f"{existing}\n\n{body}".strip() if existing else body

    if preamble:
        subjective = sections["subjective"]
        sections["subjective"] = (
            f"{preamble}\n\n{subjective}".strip() if subjective else preamble
        )
    return sections


def sections_as_list(sections: dict[str, str]) -> list[dict[str, str]]:
    return [
        {"section_type": name, "ai_generated_text": sections.get(name) or ""}
        for name in SECTION_ORDER
    ]


def sections_to_markdown(sections: dict[str, str]) -> str:
    parts = ["# MEDICAL SOAP NOTE", ""]
    for name in SECTION_ORDER:
        parts.append(_TITLES[name])
        parts.append("")
        parts.append(sections.get(name) or "")
        parts.append("")
    return "\n".join(parts).strip() + "\n"
