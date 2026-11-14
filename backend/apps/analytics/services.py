import ipaddress
import re
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import DIRECT, VISIT_GAP, PageView, Visitor

BOT_UA = re.compile(r"bot|crawl|spider|slurp|headless|lighthouse|preview|facebookexternalhit", re.I)
CHART_DAYS = 14
WINDOW_DAYS = 30
# Lifetime visit counts, grouped for the "how often they come back" bars.
# How long visit records are kept — the privacy notice (frontend
# src/routes/public/Privacy.jsx) promises this, so change both together.
RETENTION = timedelta(days=395)  # ~13 months
IP_RETENTION = timedelta(days=90)  # IP address + country on each page view
FREQUENCY_BUCKETS = (("Once", 1, 1), ("2–3 times", 2, 3), ("4–9 times", 4, 9), ("10+ times", 10, None))


def is_bot(user_agent: str) -> bool:
    return not user_agent or bool(BOT_UA.search(user_agent))


def _valid_ip(value: str):
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(meta) -> str | None:
    """The visitor's IP. Render serves through Cloudflare, which sets
    CF-Connecting-IP; otherwise the first X-Forwarded-For hop, then the
    socket address. Headers can be forged by a client that bypasses the
    proxy, so treat this as a log, not proof of identity."""
    for header in ("HTTP_CF_CONNECTING_IP", "HTTP_TRUE_CLIENT_IP"):
        if ip := _valid_ip(meta.get(header, "")):
            return ip
    forwarded = meta.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded and (ip := _valid_ip(forwarded.split(",")[0])):
        return ip
    return _valid_ip(meta.get("REMOTE_ADDR", ""))


def client_country(meta) -> str:
    """Cloudflare's CF-IPCountry, when present. 'XX' (unknown) and 'T1' (Tor) are dropped."""
    code = meta.get("HTTP_CF_IPCOUNTRY", "").strip().upper()
    return code if len(code) == 2 and code.isalpha() and code != "XX" else ""


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def _own_hosts() -> set:
    urls = [settings.FRONTEND_URL, *settings.CORS_ALLOWED_ORIGINS]
    return {_host(u) for u in urls if u}


def traffic_source(referrer: str = "", utm_source: str = "") -> str:
    """'google.com', a utm_source tag, or 'Direct'. Links within EEL count as direct."""
    if utm_source.strip():
        return utm_source.strip().lower()[:100]
    host = _host(referrer) if referrer else ""
    if not host or host in _own_hosts():
        return DIRECT
    return host[:100]


def record_page_view(
    *, visitor_id, path, referrer="", utm_source="", user=None, ip_address=None, country="", now=None,
) -> PageView:
    now = now or timezone.now()
    with transaction.atomic():
        visitor, created = Visitor.objects.select_for_update().get_or_create(
            id=visitor_id, defaults={"first_seen": now, "last_seen": now},
        )
        starts_visit = created or now - visitor.last_seen > VISIT_GAP
        source = traffic_source(referrer, utm_source) if starts_visit else ""

        updates = {"last_seen": now}
        if starts_visit:
            updates["visit_count"] = F("visit_count") + 1
        if created:
            updates["first_source"] = source
        if user and visitor.user_id != user.pk:
            updates["user"] = user
        Visitor.objects.filter(pk=visitor.pk).update(**updates)

        return PageView.objects.create(
            visitor=visitor, path=path[:300], starts_visit=starts_visit, source=source,
            ip_address=ip_address, country=country, created_at=now,
        )


def prune_old_data(now=None) -> tuple[int, int]:
    """Erase IPs past IP_RETENTION, delete page views past RETENTION, then
    visitors not seen since. Returns (views deleted, visitors deleted)."""
    now = now or timezone.now()
    PageView.objects.filter(created_at__lt=now - IP_RETENTION).exclude(ip_address=None, country="").update(
        ip_address=None, country="",
    )
    cutoff = now - RETENTION
    views, _ = PageView.objects.filter(created_at__lt=cutoff).delete()
    visitors, _ = Visitor.objects.filter(last_seen__lt=cutoff).delete()
    return views, visitors


def _ranked(rows, key, limit):
    rows = list(rows[:limit])
    top = max((r["n"] for r in rows), default=0) or 1
    for r in rows:
        r["label"] = r[key]
        r["pct"] = round(r["n"] * 100 / top)
    return rows


def visitor_stats(now=None) -> dict:
    """Numbers for the admin dashboard's Visitors section."""
    now = now or timezone.now()
    start = now - timedelta(days=WINDOW_DAYS)
    active = Visitor.objects.filter(last_seen__gte=start)
    counts = active.aggregate(
        total=Count("pk"),
        week=Count("pk", filter=Q(last_seen__gte=now - timedelta(days=7))),
        new=Count("pk", filter=Q(first_seen__gte=start)),
        returning=Count("pk", filter=Q(visit_count__gte=2)),
    )
    views = PageView.objects.filter(created_at__gte=start)

    frequency = []
    for label, low, high in FREQUENCY_BUCKETS:
        q = Q(visit_count__gte=low) & (Q(visit_count__lte=high) if high else Q())
        frequency.append({"label": label, "n": active.filter(q).count()})
    top = max((b["n"] for b in frequency), default=0) or 1
    for b in frequency:
        b["pct"] = round(b["n"] * 100 / top)

    chart_start = (now - timedelta(days=CHART_DAYS - 1)).date()
    per_day = dict(
        PageView.objects.filter(created_at__date__gte=chart_start)
        .annotate(day=TruncDate("created_at"))
        .values_list("day")
        .annotate(n=Count("visitor", distinct=True))
    )
    peak = max(per_day.values(), default=0) or 1
    daily = []
    for i in range(CHART_DAYS):
        d = chart_start + timedelta(days=i)
        daily.append({"day": d, "count": per_day.get(d, 0), "pct": round(per_day.get(d, 0) * 100 / peak)})

    return {
        **counts,
        "returning_pct": round(counts["returning"] * 100 / counts["total"]) if counts["total"] else 0,
        "visits": views.filter(starts_visit=True).count(),
        "page_views": views.count(),
        "frequency": frequency,
        "daily": daily,
        "sources": _ranked(
            views.filter(starts_visit=True).values("source").annotate(n=Count("id")).order_by("-n", "source"), "source", 8,
        ),
        "pages": _ranked(views.values("path").annotate(n=Count("id")).order_by("-n", "path"), "path", 8),
    }
