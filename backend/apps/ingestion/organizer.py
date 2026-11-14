"""
Find the organiser's own link inside an aggregator's write-up.

RSS sources are mostly aggregators (Opportunity Desk, Opportunities for
Africans, ReliefWeb …): an item's <link> is *their* article about the
opportunity, not the opportunity itself. Every such article links out to
the organiser somewhere in its body, and the link is labelled the same
handful of ways across sites:

    "Click here to apply"                    opportunitydesk.org
    "Visit the Official Webpage of …"        opportunitiesforafricans.com
    "Apply here" / "Official programme …"    opportunitiesforyouth.org
    "VISIT HERE TO APPLY FOR …"              opportunitiescorners.com
    https://apply.workable.com/… (bare URL)  reliefweb.int "How to apply"
    "CLICK <a>HERE</a> TO APPLY"             generic link text: judged by its sentence
    "Pour postuler … <a>ici</a>"             French/Spanish/Portuguese postings
    "CLICK <a>HERE</a> TO APPLY"             generic link text: judged by its sentence
    "Pour postuler … <a>ici</a>"             French/Spanish/Portuguese postings

So: collect outbound links from the article body, drop share buttons and
links back to the aggregator itself, score what's left by its anchor
text, and take the best. No match means no change — the listing keeps
the aggregator's URL, which is still a working page about it.
"""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

APPLY_WORDS = re.compile(
    r"\b(apply|application|applications|register|registration|submit|nominate|nominations?"
    r"|postuler|postulez|candidater|candidature|candidatures|inscription|inscrivez"  # fr
    r"|postular|postulación|solicitar|solicitud|aplicar|inscripción|inscribirse"     # es
    r"|candidatar|candidatura|candidaturas|inscrição|inscrever)\b",                 # pt
    re.IGNORECASE,
)
OFFICIAL_WORDS = re.compile(r"\b(official|officiel|officielle|oficial)\b", re.IGNORECASE)
# Link text that says nothing on its own; the sentence around it decides.
GENERIC_TEXT = re.compile(
    r"^(click\s+|cliquez\s+|clique\s+|haga\s+clic\s+)?"
    r"(here|ici|aqu[ií]|this\s+link|the\s+link|link|this\s+form|the\s+form|form|online|en\s+ligne)\W*$",
    re.IGNORECASE,
)
CONTEXT_BEFORE, CONTEXT_AFTER = 160, 80  # characters of surrounding text read for generic links

# Share buttons, comment widgets and site chrome that sit inside articles.
IGNORED_HOSTS = {
    "facebook.com", "twitter.com", "x.com", "linkedin.com", "whatsapp.com", "wa.me", "t.me", "telegram.me",
    "telegram.org", "instagram.com", "youtube.com", "youtu.be", "pinterest.com", "tumblr.com", "reddit.com",
    "m.me", "messenger.com", "akismet.com", "gravatar.com", "wordpress.org", "wordpress.com", "wp.com",
    "elegantthemes.com", "addtoany.com", "sharethis.com",
}
# Second-level labels under country TLDs: jobs.example.com.gh -> example.com.gh
_SHORT_SLDS = {"co", "com", "org", "net", "ac", "gov", "edu", "or", "ne", "go"}

# Content regions win over everything else; chrome regions never count.
_CONTENT_TAGS = {"article", "main"}
_CHROME_TAGS = {"nav", "header", "footer", "aside"}


def site_domain(url_or_host: str) -> str:
    """Registrable domain, near enough: 'www.jobs.example.com.gh' -> 'example.com.gh'."""
    host = (urlparse(url_or_host).hostname if "//" in url_or_host else url_or_host) or ""
    labels = host.lower().rstrip(".").split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SHORT_SLDS:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        # (href, anchor text, inside article/main, start, end) — start/end
        # are offsets into the page's running text, for reading context.
        self.links: list[tuple[str, str, bool, int, int]] = []
        self.text: list[str] = []
        self._length = 0
        self._content_depth = 0
        self._chrome_depth = 0
        self._href: str | None = None
        self._anchor: list[str] = []
        self._start = 0

    def handle_starttag(self, tag, attrs):
        if tag in _CONTENT_TAGS:
            self._content_depth += 1
        elif tag in _CHROME_TAGS:
            self._chrome_depth += 1
        elif tag == "a" and not self._chrome_depth:
            self._href = dict(attrs).get("href") or ""
            self._anchor = []
            self._start = self._length

    def handle_endtag(self, tag):
        if tag in _CONTENT_TAGS:
            self._content_depth = max(0, self._content_depth - 1)
        elif tag in _CHROME_TAGS:
            self._chrome_depth = max(0, self._chrome_depth - 1)
        elif tag == "a" and self._href is not None:
            text = " ".join("".join(self._anchor).split())
            self.links.append((self._href, text, self._content_depth > 0, self._start, self._length))
            self._href = None

    def handle_data(self, data):
        if self._href is not None:
            self._anchor.append(data)
        self.text.append(data)
        self._length += len(data)


def _score(text: str, href: str, context: str) -> int:
    if APPLY_WORDS.search(text):
        return 3
    if OFFICIAL_WORDS.search(text):
        return 2
    if GENERIC_TEXT.match(text) and APPLY_WORDS.search(context):
        return 2
    if text.rstrip("/") == href.rstrip("/") or text.startswith(("http://", "https://", "www.")):
        return 1  # the URL spelled out, as in ReliefWeb's "How to apply"
    return 0


def find_organizer_url(html: str, page_url: str, also_ignore: tuple[str, ...] = ()) -> str:
    """The organiser's link from an aggregator page, or "" if there isn't a clear one.

    `also_ignore` takes extra URLs whose sites are the aggregator too
    (e.g. the feed URL, when the feed and articles live on different hosts)."""
    parser = _LinkParser()
    parser.feed(html)
    parser.close()

    own_sites = {site_domain(page_url), *(site_domain(u) for u in also_ignore if u)}
    page_text = "".join(parser.text)
    candidates = []
    for position, (href, text, in_content, start, end) in enumerate(parser.links):
        url = urljoin(page_url, href.strip())
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or len(url) > 500:
            continue
        site = site_domain(url)
        if site in own_sites or site in IGNORED_HOSTS or parsed.hostname.lower() in IGNORED_HOSTS:
            continue
        context = " ".join(page_text[max(0, start - CONTEXT_BEFORE):end + CONTEXT_AFTER].split())
        score = _score(text, href.strip(), context)
        if score:
            # Article body beats anything else on the page; then score; then first in reading order.
            candidates.append((in_content, score, -position, url))

    return max(candidates)[3] if candidates else ""
