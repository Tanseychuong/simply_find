import uuid
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.analytics.countries import country_name
from apps.analytics.models import DIRECT, PageView, Visitor
from apps.analytics.services import IP_RETENTION, RETENTION, client_ip, prune_old_data, record_page_view, traffic_source, visitor_stats

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
HIT_URL = "/api/analytics/hit/"


def hit(api_client, visitor_id, path="/", ua=BROWSER_UA, **extra):
    headers = {k: extra.pop(k) for k in list(extra) if k.startswith("HTTP_")}
    return api_client.post(
        HIT_URL, {"visitor_id": str(visitor_id), "path": path, **extra}, format="json", HTTP_USER_AGENT=ua, **headers,
    )


class TestClientIp:
    def test_prefers_cloudflare_then_forwarded_then_socket(self):
        assert client_ip({"HTTP_CF_CONNECTING_IP": "198.51.100.1", "REMOTE_ADDR": "10.0.0.1"}) == "198.51.100.1"
        assert client_ip({"HTTP_X_FORWARDED_FOR": "198.51.100.2, 10.0.0.9", "REMOTE_ADDR": "10.0.0.1"}) == "198.51.100.2"
        assert client_ip({"REMOTE_ADDR": "10.0.0.1"}) == "10.0.0.1"

    def test_garbage_is_ignored(self):
        assert client_ip({"HTTP_X_FORWARDED_FOR": "<script>", "REMOTE_ADDR": ""}) is None


class TestTrafficSource:
    def test_referrer_host_without_www(self):
        assert traffic_source("https://www.Google.com/search?q=eel") == "google.com"

    def test_utm_source_wins_over_referrer(self):
        assert traffic_source("https://t.co/abc", "WhatsApp") == "whatsapp"

    def test_no_referrer_or_own_site_is_direct(self, settings):
        settings.FRONTEND_URL = "https://simplyfind.example"
        assert traffic_source("") == DIRECT
        assert traffic_source("https://simplyfind.example/opportunities") == DIRECT


@pytest.mark.django_db
class TestRecordPageView:
    def test_first_view_creates_visitor_and_starts_a_visit(self):
        vid = uuid.uuid4()
        view = record_page_view(visitor_id=vid, path="/", referrer="https://www.linkedin.com/feed/")
        visitor = Visitor.objects.get(pk=vid)
        assert view.starts_visit and view.source == "linkedin.com"
        assert visitor.visit_count == 1 and visitor.first_source == "linkedin.com"

    def test_views_close_together_are_one_visit(self):
        vid, now = uuid.uuid4(), timezone.now()
        record_page_view(visitor_id=vid, path="/", now=now)
        second = record_page_view(visitor_id=vid, path="/opportunities", now=now + timedelta(minutes=10))
        assert not second.starts_visit and second.source == ""
        assert Visitor.objects.get(pk=vid).visit_count == 1

    def test_coming_back_after_a_gap_is_a_new_visit(self):
        vid, now = uuid.uuid4(), timezone.now()
        record_page_view(visitor_id=vid, path="/", referrer="https://google.com/", now=now)
        back = record_page_view(visitor_id=vid, path="/", referrer="https://facebook.com/", now=now + timedelta(days=2))
        visitor = Visitor.objects.get(pk=vid)
        assert back.starts_visit and back.source == "facebook.com"
        assert visitor.visit_count == 2 and visitor.first_source == "google.com"

    def test_links_the_member_when_logged_in(self, user):
        vid = uuid.uuid4()
        record_page_view(visitor_id=vid, path="/", user=user)
        assert Visitor.objects.get(pk=vid).user == user


@pytest.mark.django_db
class TestHitEndpoint:
    def test_records_anonymous_hit(self, api_client):
        vid = uuid.uuid4()
        response = hit(api_client, vid, "/opportunities", referrer="https://www.google.com/")
        assert response.status_code == 204
        assert PageView.objects.get().source == "google.com"

    def test_logs_ip_and_country_from_the_proxy(self, api_client):
        hit(api_client, uuid.uuid4(), HTTP_CF_CONNECTING_IP="203.0.113.7", HTTP_CF_IPCOUNTRY="gh")
        view = PageView.objects.get()
        assert view.ip_address == "203.0.113.7" and view.country == "GH"

    def test_ignores_bots(self, api_client):
        assert hit(api_client, uuid.uuid4(), ua="Googlebot/2.1 (+http://www.google.com/bot.html)").status_code == 204
        assert not PageView.objects.exists()

    def test_bad_payload_is_silently_dropped(self, api_client):
        response = api_client.post(HIT_URL, {"visitor_id": "not-a-uuid", "path": "/"}, format="json", HTTP_USER_AGENT=BROWSER_UA)
        assert response.status_code == 204
        assert not Visitor.objects.exists()

    def test_long_paths_are_trimmed(self, api_client):
        hit(api_client, uuid.uuid4(), "/" + "a" * 1000)
        assert len(PageView.objects.get().path) == 300


@pytest.mark.django_db
class TestVisitorStats:
    def test_counts_returning_visitors_and_sources(self):
        now = timezone.now()
        loyal, once = uuid.uuid4(), uuid.uuid4()
        record_page_view(visitor_id=loyal, path="/", referrer="https://google.com/", now=now - timedelta(days=3))
        record_page_view(visitor_id=loyal, path="/opportunities", now=now - timedelta(days=1))
        record_page_view(visitor_id=once, path="/", referrer="https://google.com/", now=now)

        stats = visitor_stats(now)
        assert stats["total"] == 2 and stats["returning"] == 1 and stats["returning_pct"] == 50
        assert stats["visits"] == 3 and stats["page_views"] == 3
        assert [(s["label"], s["n"]) for s in stats["sources"]] == [("google.com", 2), (DIRECT, 1)]
        assert {b["label"]: b["n"] for b in stats["frequency"]}["2–3 times"] == 1

    def test_dashboard_shows_visitors_to_admins_only(self, admin_user, moderator_user):
        record_page_view(visitor_id=uuid.uuid4(), path="/")
        admin = Client()
        admin.force_login(admin_user)
        response = admin.get("/admin/")
        assert response.context["dash"]["visitors"]["total"] == 1
        assert "Where visits come from" in response.content.decode()

        moderator = Client()
        moderator.force_login(moderator_user)
        assert "visitors" not in moderator.get("/admin/").context["dash"]


@pytest.mark.django_db
def test_prune_deletes_only_data_past_retention():
    now = timezone.now()
    old, recent = uuid.uuid4(), uuid.uuid4()
    record_page_view(visitor_id=old, path="/", now=now - RETENTION - timedelta(days=1))
    record_page_view(visitor_id=recent, path="/", now=now - RETENTION - timedelta(days=1))
    record_page_view(visitor_id=recent, path="/", now=now)

    assert prune_old_data(now) == (2, 1)
    assert list(Visitor.objects.values_list("pk", flat=True)) == [recent]
    assert PageView.objects.count() == 1


@pytest.mark.django_db
def test_prune_erases_ip_after_ip_retention_but_keeps_the_view():
    now = timezone.now()
    record_page_view(visitor_id=uuid.uuid4(), path="/", ip_address="203.0.113.7", country="GH",
                     now=now - IP_RETENTION - timedelta(days=1))
    prune_old_data(now)
    view = PageView.objects.get()
    assert view.ip_address is None and view.country == ""


def test_country_name():
    assert country_name("GH") == "Ghana"
    assert country_name("cd") == "Democratic Republic of the Congo"
    assert country_name("TZ") == "Tanzania"
    assert country_name("ZZ") == "ZZ"
    assert country_name("") == ""


@pytest.mark.django_db
def test_admin_shows_country_names(admin_user):
    record_page_view(visitor_id=uuid.uuid4(), path="/", country="NG")
    record_page_view(visitor_id=uuid.uuid4(), path="/", country="GH")
    record_page_view(visitor_id=uuid.uuid4(), path="/")
    admin = Client()
    admin.force_login(admin_user)

    page = admin.get("/admin/analytics/pageview/").content.decode()
    assert "Ghana (GH)" in page and "Nigeria (NG)" in page
    assert page.index(">Ghana</a>") < page.index(">Nigeria</a>")  # filter, by name

    filtered = admin.get("/admin/analytics/pageview/?country=GH").content.decode()
    assert "Ghana (GH)" in filtered and "Nigeria (NG)" not in filtered

    view = PageView.objects.get(country="NG")
    assert "Nigeria (NG)" in admin.get(f"/admin/analytics/pageview/{view.pk}/change/").content.decode()
