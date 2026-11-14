"""
The structured description of an opportunity: named sections, each a list
of blocks, stored in Opportunity.sections and rendered by the detail page.

    [{"kind": "eligibility", "title": "Eligibility",
      "blocks": [{"type": "p", "text": "Open to ..."},
                 {"type": "li", "text": "Aged 18-35"},
                 {"type": "h", "text": "Education"}]}]

Blocks are plain text — never HTML — so nothing a source or submitter
writes is ever injected into the page. Fetched listings get their
sections from the source's HTML (apps/ingestion/sections.py); submitted
ones from the form's optional fields (text_to_blocks below).
"""

import re

# kind -> display title, in the order the detail page shows them.
KINDS = {
    "overview": "About this opportunity",
    "organization": "About the organisation",
    "eligibility": "Eligibility",
    "responsibilities": "What the role involves",
    "benefits": "Benefits",
    "documents": "Required documents",
    "how_to_apply": "How to apply",
    "dates": "Deadline and key dates",
}
OTHER = "other"  # a source heading that fits none of the above; keeps its own title
BLOCK_TYPES = {"p", "li", "h"}

MAX_SECTIONS = 12
MAX_BLOCKS = 80
MAX_BLOCK_TEXT = 1500
MAX_SECTION_TEXT = 5000   # a long "Benefits" can't crowd out "Eligibility"
MAX_TOTAL_TEXT = 30000

_BULLET = re.compile(r"^\s*(?:[-*•·▪◦‣–]|\d{1,2}[.)])\s+")


def text_to_blocks(text: str) -> list[dict]:
    """Free text from a form -> blocks: one paragraph per line, bullets
    ("- ", "* ", "• ", "1. ") become list items."""
    blocks = []
    for line in (text or "").splitlines():
        line = " ".join(line.split())
        if not line:
            continue
        if _BULLET.match(line):
            blocks.append({"type": "li", "text": _BULLET.sub("", line, count=1)[:MAX_BLOCK_TEXT]})
        else:
            blocks.append({"type": "p", "text": line[:MAX_BLOCK_TEXT]})
    return blocks[:MAX_BLOCKS]


def as_text(sections) -> str:
    """All of the sections' text, one block per line (for searching it,
    e.g. for a "Deadline: …" line)."""
    return "\n".join(
        block.get("text", "")
        for section in sections or [] if isinstance(section, dict)
        for block in section.get("blocks") or [] if isinstance(block, dict)
    )


def ordered(sections: list[dict]) -> list[dict]:
    """Known kinds in KINDS order, then any others in their original order."""
    rank = {kind: i for i, kind in enumerate(KINDS)}
    return sorted(sections, key=lambda s: rank.get(s["kind"], len(rank)))


def clean_sections(sections) -> list[dict]:
    """Normalise anything claiming to be sections (a source, a form, the
    admin's JSON editor) into the stored shape, dropping what doesn't fit."""
    candidates = [
        {**s, "kind": s.get("kind") if s.get("kind") in KINDS else OTHER}
        for s in (sections if isinstance(sections, list) else []) if isinstance(s, dict)
    ]
    cleaned, total = [], 0
    # Budget in display order, so the standard sections always fit first.
    for section in ordered(candidates):
        kind = section["kind"]
        title = KINDS.get(kind) or " ".join(str(section.get("title") or "").split())[:120]
        if not title:
            continue
        blocks, used = [], 0
        for block in section.get("blocks") or []:
            if not isinstance(block, dict) or block.get("type") not in BLOCK_TYPES:
                continue
            text = " ".join(str(block.get("text") or "").split())[:MAX_BLOCK_TEXT]
            if not text:
                continue
            if (len(blocks) == MAX_BLOCKS or used + len(text) > MAX_SECTION_TEXT
                    or total + len(text) > MAX_TOTAL_TEXT):
                break
            blocks.append({"type": block["type"], "text": text})
            used += len(text)
            total += len(text)
        while blocks and blocks[-1]["type"] == "h":  # a cut-off section shouldn't end on a sub-heading
            blocks.pop()
        if blocks:
            cleaned.append({"kind": kind, "title": title, "blocks": blocks})
    return cleaned[:MAX_SECTIONS]
