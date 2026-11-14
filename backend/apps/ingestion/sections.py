"""
Turn a source's HTML into the sections stored on Opportunity.sections
(apps/opportunities/sections.py describes the shape).

Sources already organise their write-ups under headings — "About One Acre
Fund", "Who Can Apply?", "Benefits", "How to Apply" — but mark them up
every which way: real <h2>/<h3>, a paragraph that's all <strong>, or a
bold label at the start of a paragraph ("<strong>Eligibility:</strong>
Open to ..."). So:

  1. Read the HTML into a flat run of headings and text blocks, skipping
     page chrome (nav, share buttons, related posts, comments, forms).
  2. Name each heading with one of the standard kinds by its wording.
     Headings that match none become sections of their own, unless they
     sit below the current section's heading level ("1. Full Tuition
     Coverage" under "Benefits"), in which case they're a sub-heading.
  3. Text before the first heading is the overview.

Nothing is returned unless at least one standard section beyond the
overview was found — then the plain description is the better display.
"""

import re
from html.parser import HTMLParser

from apps.opportunities.sections import KINDS, OTHER, clean_sections

# First match wins, so the order matters: "Application Deadline" is a
# date, "Who can apply?" is eligibility, "About the role" is the overview
# while "About One Acre Fund" is the organisation.
_RULES = [
    ("dates", r"deadline|closing date|key dates|important dates|timeline|start date|when to apply"
              r"|fecha l[ií]mite|date limite|date de cl[oô]ture"),
    ("documents", r"documents|materials|what to submit|documentos|pi[eè]ces"),
    ("eligibility", r"eligib|requirement|criteria|qualification|who can|who should|looking for|about you"
                    r"|your profile|candidate profile|right match|must have|competenc|skills|desirable"
                    r"|elegib|requisitos|perfil|deseable|exigences|profil|admissib|crit[eè]res|souhait"
                    r"|languages?\b|idiomas|langues"),
    ("how_to_apply", r"how to apply|to apply|\bapply\b|application|recruitment process|selection process"
                     r"|next steps|submission|postular|postuler|solicitud|candidature|c[oó]mo aplicar"
                     r"|proceso de selecci[oó]n|processus de recrutement"),
    ("overview", r"^about\b.*\b(role|job|position|program|programme|fellowship|scholarship|grant|award"
                 r"|prize|internship|opportunity|call|competition|course|project|initiative|conference|summit"
                 r"|training|bootcamp|challenge|hackathon)"
                 r"|^what is|overview|objetivo del cargo|descripci[oó]n del (puesto|cargo)"
                 r"|description du poste|contexte"),
    ("responsibilities", r"responsibilit|duties|what you.ll do|what you will do|key tasks|scope of work"
                         r"|key outputs|deliverables|the role involves|responsabilidades|funciones"
                         r"|responsabilit[eé]s|t[aâ]ches|missions"),
    ("benefits", r"benefit|funding|stipend|award|prize|what you.ll get|what you will get|we offer|compensation"
                 r"|salary|remuneration|perks|coverage|financial|package|employment conditions"
                 r"|ofrecemos|beneficios|salario|nous offrons|avantages|r[eé]mun[eé]ration|conditions d.emploi"),
    ("overview", r"description|summary|introduction|background|details|the role\b|the opportunity"),
    ("organization", r"^about\b|who we are|mission|vision|our story|the organi[sz]ation|the company"
                     r"|acerca de|qui[eé]nes somos|qui sommes|[aà] propos"),
]
_RULES = [(kind, re.compile(pattern)) for kind, pattern in _RULES]

# Headings (and everything under them) that are the site's, not the listing's.
_JUNK_HEADING = re.compile(
    r"^(share|related|you may also|also read|read also|see also|similar|more opportunities|comments?\b"
    r"|leave a (reply|comment)|subscribe|newsletter|follow us|join our|disclaimer|advert|recommended"
    r"|popular|tags\b|about the author|post navigation|trending|latest (posts|opportunities))"
    r"|\brelated (posts|articles|opportunities|jobs)|\bdiscover more\b",
)
_JUNK_TEXT = re.compile(
    r"appeared first on|^(share|tweet|pin it)\b|click here to join|join our (whatsapp|telegram)"
    r"|subscribe to|follow us on|^advertisement$|^\d+$"
    # A link's label on its own ("Click here to apply") means nothing without
    # the link; the page's Apply button covers it.
    r"|^(click here|visit here|apply here|apply now|click to apply)\b[\w\s'’-]{0,60}$",
    re.IGNORECASE,
)

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_BLOCK = {"p", "div", "li", "td", "th", "dd", "dt", "blockquote", "section", "article", "tr", "pre",
          "ul", "ol", "table", "figcaption", "main", "header", "footer"}
_HEADINGS = {f"h{n}": n for n in range(1, 7)}
_SKIP_TAGS = {"nav", "header", "footer", "aside", "script", "style", "noscript", "form", "figure", "button",
              "select", "svg", "iframe", "template"}
_SKIP_CLASS = re.compile(
    r"share|social|related|comment|sidebar|widget|newsletter|subscribe|advert|^ads?$|^ad-|author|breadcrumb"
    r"|navigation|menu|sharedaddy|jp-relatedposts|post-meta|entry-meta|cookie|popup|modal|tags"
)
_CONTENT_CLASS = re.compile(
    r"entry-content|post-content|article-content|post-body|article-body|single-content|td-post-content"
    r"|job-description|job__description|posting-page|field--name-body"
)
_CONTENT_MARKUP = re.compile(r"""(class|id)=["'][^"']*(""" + _CONTENT_CLASS.pattern + r")", re.IGNORECASE)
_NUMBERED = re.compile(r"^(?:(\d{1,2})[.):]|step (\d+)\b:?|[ivx]{1,4}[.)])\s", re.IGNORECASE)


def _number(heading: str) -> int | None:
    match = _NUMBERED.match(heading)
    if not match:
        return None
    digits = match.group(1) or match.group(2)
    return int(digits) if digits else 0  # roman numerals: numbered, but not counted
BOLD_HEADING_MAX = 90
LABEL_MAX = 60
SUB_LEVEL = 7  # bold-paragraph "headings" rank below every <hN>


def classify(heading: str) -> str:
    text = heading.lower().replace("’", "'").strip(" :.?!")
    if len(text) > 120:
        return OTHER
    for kind, pattern in _RULES:
        if pattern.search(text):
            return kind
    return OTHER


class _Reader(HTMLParser):
    """HTML -> [("heading", level, text) | ("block", "p"|"li", text)]."""

    def __init__(self, page: bool, strict: bool = False):
        super().__init__(convert_charrefs=True)
        self.page = page  # a whole web page: only read its article/main content
        # The page marks its post body (entry-content …): read only that, not
        # every <article> — related-post cards are <article>s too.
        self.strict = strict
        self.events: list[tuple] = []
        self.found_content = False
        self._stack: list[tuple[str, bool, bool]] = []  # (tag, skip, content)
        self._parts: list[tuple[str, bool]] = []         # (text, inside <strong>/<b>)
        self._bold = 0
        self._kind = "p"
        self._level = 0

    # --- where are we -------------------------------------------------------

    def _skipping(self) -> bool:
        return any(skip for _, skip, _ in self._stack)

    def _reading(self) -> bool:
        if self._skipping():
            return False
        return not self.page or any(content for _, _, content in self._stack)

    # --- tags ---------------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self._flush()
            return
        if tag in _VOID:
            return
        attrs = dict(attrs)
        tokens = f"{attrs.get('class') or ''} {attrs.get('id') or ''}".lower().split()
        inside = not self.page or any(c for _, _, c in self._stack)
        content = any(_CONTENT_CLASS.search(t) for t in tokens) or (
            not self.strict and tag in ("article", "main"))
        # Chrome classes only count inside the content: outside it nothing
        # is read anyway, and wrappers like <div class="has-sidebar"> hold
        # the whole article.
        skip = tag in _SKIP_TAGS or (inside and not content and any(_SKIP_CLASS.search(t) for t in tokens))
        if content and not skip:
            self.found_content = True
        if tag in _BLOCK or tag in _HEADINGS:
            self._flush()
        if tag == "li":
            self._kind = "li"
        elif tag in _HEADINGS:
            self._kind, self._level = "h", _HEADINGS[tag]
        elif tag in ("strong", "b"):
            self._bold += 1
        self._stack.append((tag, skip, content))

    def handle_endtag(self, tag):
        if tag in _VOID or not any(t == tag for t, _, _ in self._stack):
            return
        if tag in _BLOCK or tag in _HEADINGS:
            self._flush()
        while self._stack:
            open_tag, _, _ = self._stack.pop()
            if open_tag in ("strong", "b"):
                self._bold = max(0, self._bold - 1)
            if open_tag == tag:
                break

    def handle_data(self, data):
        if self._reading():
            self._parts.append((data, self._bold > 0))

    def close(self):
        super().close()
        self._flush()

    # --- one block of text --------------------------------------------------

    def _flush(self):
        parts, kind, level = self._parts, self._kind, self._level
        self._parts, self._kind, self._level = [], "p", 0
        text = " ".join("".join(t for t, _ in parts).split())
        if not text or _JUNK_TEXT.search(text):
            return
        if kind == "h" and len(text) <= 120:
            self.events.append(("heading", level, text))
            return
        if kind == "li":
            self.events.append(("block", "li", text))
            return

        bold = " ".join("".join(t for t, b in parts if b).split())
        label, _, value = text.partition(":")
        if (bold == text and value.strip() and len(label) <= LABEL_MAX and not _NUMBERED.match(text)
                and classify(label) != OTHER):
            self.events.append(("label", classify(label), text))  # "<strong>Deadline: 17 Nov</strong>"
            return
        if bold == text and len(text) <= BOLD_HEADING_MAX and not text.endswith("."):
            self.events.append(("heading", SUB_LEVEL, text))
            return
        # "<strong>Deadline:</strong> 17 November" — a one-line fact filed
        # under its section, without pulling the paragraphs after it along.
        lead = ""
        for t, b in parts:
            if not b:
                break
            lead += t
        lead = " ".join(lead.split())
        if lead.endswith(":") and len(lead) <= LABEL_MAX and lead != text and classify(lead) != OTHER:
            self.events.append(("label", classify(lead), text))
            return
        if text.startswith(("• ", "· ", "- ", "– ")):
            self.events.append(("block", "li", text[2:].strip()))
        else:
            self.events.append(("block", "p", text))


def extract_sections(html: str, page: bool = False) -> list[dict]:
    """Sections from an HTML fragment (a feed item's or job API's content),
    or, with page=True, from the article/main part of a whole web page."""
    if not html:
        return []
    reader = _Reader(page=page, strict=page and bool(_CONTENT_MARKUP.search(html)))
    reader.feed(html)
    reader.close()
    if page and not reader.found_content:
        return []

    sections: list[dict] = []
    by_kind: dict[str, dict] = {}
    current = None
    numbered = None  # (section, level, number) of the last numbered sub-heading

    def section_for(kind, title, level):
        if kind in KINDS and kind in by_kind:  # a second "Eligibility" heading adds to the first
            found = by_kind[kind]
            found["level"] = min(found["level"], level)
            return found
        found = {"kind": kind, "title": title, "level": level, "blocks": []}
        sections.append(found)
        if kind in KINDS:
            by_kind[kind] = found
        return found

    def start(kind, title, level):
        nonlocal current
        current = section_for(kind, title, level)

    for event in reader.events:
        if event[0] == "label":
            _, kind, text = event
            section_for(kind, KINDS[kind], 99)["blocks"].append({"type": "p", "text": text})
        elif event[0] == "heading":
            _, level, text = event
            kind = classify(text)
            if _JUNK_HEADING.search(text.lower()) and kind == OTHER:
                current = {"kind": "junk", "title": "", "level": level, "blocks": []}  # swallowed, never kept
                continue
            deeper = current is not None and current["kind"] != "junk" and level > current["level"]
            number = _number(text)
            continues = (number and numbered and numbered[1] == level and number == numbered[2] + 1
                         and numbered[0] is not current)
            if continues:
                # "5. Summer Internships" continues the list "4. …" was in,
                # even when a stray heading came in between.
                current = numbered[0]
                current["blocks"].append({"type": "h", "text": text})
            # Below the current heading, unknown headings, numbered points
            # ("2. Annual Stipends …", "Step 3: …") and FAQ-style questions
            # are sub-headings of it, even when their wording matches a kind.
            elif deeper and (kind == OTHER or number is not None
                             or (current["kind"] == OTHER and text.endswith("?"))):
                current["blocks"].append({"type": "h", "text": text})
            elif current is not None and kind == current["kind"]:
                current["blocks"].append({"type": "h", "text": text})
            elif kind == OTHER:
                # An unknown heading at the very top is usually the title itself.
                if current is None:
                    start("overview", KINDS["overview"], 99)
                else:
                    start(OTHER, text, level)
            else:
                start(kind, KINDS[kind], level)
            if number and not continues and current is not None:
                numbered = (current, level, number)
            elif continues:
                numbered = (current, level, number)
        else:
            _, block_type, text = event
            if current is None:
                start("overview", KINDS["overview"], 99)  # text before the first heading
            current["blocks"].append({"type": block_type, "text": text})

    kept = [s for s in sections if s["kind"] != "junk"]
    others = [s for s in kept if s["kind"] == OTHER]
    kept = [s for s in kept if s["kind"] != OTHER or s in others[:4]]
    if not any(s["kind"] not in ("overview", OTHER) for s in kept):
        return []
    return clean_sections(kept)
