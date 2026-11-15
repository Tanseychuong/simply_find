"""SimplyFind's scope: internships, graduate programmes and entry-level
roles for students and recent graduates, plus an opt-in graduate school tab."""

import pytest

from apps.opportunities.models import Opportunity
from tests.test_companies import _company, _job_payload, _temp_uploads, owner, owner_client  # noqa: F401

pytestmark = pytest.mark.django_db


def _live(category, admin_user, **fields):
    opportunity = Opportunity.objects.create(category=category, description="d", **fields)
    opportunity.approve(admin_user)
    return opportunity


class TestPostingRules:
    def test_role_fields_are_saved_and_shown(self, owner_client, owner, category):
        _company(owner, verified=True)
        payload = _job_payload(
            category, role_type="graduate_programme", experience_years_max=1, graduation_year_min=2025,
            graduation_year_max=2027, is_paid=True, work_mode="hybrid", accepts_minors=False,
        )
        res = owner_client.post("/api/companies/me/jobs/", payload, format="json")
        assert res.status_code == 201, res.data
        assert res.data["role_type"] == "graduate_programme" and res.data["work_mode"] == "hybrid"
        listed = owner_client.get(f"/api/opportunities/{res.data['id']}/").data
        assert listed["graduation_year_min"] == 2025 and listed["is_paid"] is True

    def test_more_than_two_years_experience_is_refused(self, owner_client, owner, category):
        _company(owner, verified=True)
        res = owner_client.post("/api/companies/me/jobs/", _job_payload(category, experience_years_max=3), format="json")
        assert res.status_code == 400 and "experience_years_max" in res.data
        assert not Opportunity.objects.exists()

    def test_editing_cannot_raise_experience_above_the_limit(self, owner_client, owner, category):
        _company(owner, verified=True)
        job_id = owner_client.post("/api/companies/me/jobs/", _job_payload(category), format="json").data["id"]
        res = owner_client.patch(f"/api/companies/me/jobs/{job_id}/", {"experience_years_max": 5}, format="json")
        assert res.status_code == 400
        assert Opportunity.objects.get(pk=job_id).experience_years_max == 0

    def test_graduation_years_must_be_in_order(self, owner_client, owner, category):
        _company(owner, verified=True)
        payload = _job_payload(category, graduation_year_min=2027, graduation_year_max=2025)
        assert owner_client.post("/api/companies/me/jobs/", payload, format="json").status_code == 400

    def test_duration_only_kept_for_internships(self, owner_client, owner, category):
        _company(owner, verified=True)
        res = owner_client.post("/api/companies/me/jobs/",
                                _job_payload(category, role_type="entry_level", duration_months=6), format="json")
        assert res.data["duration_months"] is None

    def test_user_submissions_follow_the_same_limit(self, api_client, user, category):
        api_client.force_authenticate(user)
        res = api_client.post("/api/opportunities/", {
            "title": "Analyst", "description": "d", "category": category.id, "experience_years_max": 4,
        }, format="json")
        assert res.status_code == 400

    def test_model_clean_enforces_the_limit_for_admin_forms(self, category):
        from django.core.exceptions import ValidationError
        with pytest.raises(ValidationError):
            Opportunity(category=category, title="t", description="d", experience_years_max=3).full_clean()


class TestFeedFilters:
    def test_graduate_school_is_a_separate_tab(self, api_client, admin_user, category):
        _live(category, admin_user, title="Intern", role_type="internship")
        _live(category, admin_user, title="MSc", role_type="graduate_school")

        feed = [o["title"] for o in api_client.get("/api/opportunities/").data["results"]]
        assert feed == ["Intern"]
        tab = api_client.get("/api/opportunities/", {"role_type": "graduate_school"}).data["results"]
        assert [o["title"] for o in tab] == ["MSc"]

    def test_filters(self, api_client, admin_user, category):
        _live(category, admin_user, title="Paid remote intern", role_type="internship", is_paid=True, work_mode="remote")
        _live(category, admin_user, title="Unpaid intern", role_type="internship", is_paid=False, work_mode="on_site")
        _live(category, admin_user, title="Trainee 2025-26", role_type="graduate_programme",
              graduation_year_min=2025, graduation_year_max=2026)

        def titles(**params):
            return sorted(o["title"] for o in api_client.get("/api/opportunities/", params).data["results"])

        assert titles(paid="true") == ["Paid remote intern"]
        assert titles(work_mode="remote,hybrid") == ["Paid remote intern"]
        assert titles(role_type="graduate_programme,entry_level") == ["Trainee 2025-26"]
        assert titles(graduation_year="2027") == ["Paid remote intern", "Unpaid intern"]
        assert titles(graduation_year="2026") == ["Paid remote intern", "Trainee 2025-26", "Unpaid intern"]
        assert titles(role_type="nonsense") == titles()  # unknown values are ignored


class TestMoreFilters:
    """Employment type, career level, deadline, recency, location, duration
    and the yes/no filters added for the website's filter panel."""

    @staticmethod
    def _titles(api_client, **params):
        return sorted(o["title"] for o in api_client.get("/api/opportunities/", params).data["results"])

    def test_employment_type_and_career_level(self, api_client, admin_user, category):
        _live(category, admin_user, title="Full-time grad", employment_type="full_time", experience_years_max=0)
        _live(category, admin_user, title="Part-time role", employment_type="part_time", experience_years_max=1)
        _live(category, admin_user, title="Unstated", experience_years_max=2)

        assert self._titles(api_client, employment_type="part_time") == ["Part-time role"]
        assert self._titles(api_client, employment_type="full_time,part_time") == ["Full-time grad", "Part-time role"]
        assert self._titles(api_client, career_level="no_experience") == ["Full-time grad"]
        assert self._titles(api_client, career_level="some_experience,early_career") == ["Part-time role", "Unstated"]
        assert len(self._titles(api_client, career_level="senior")) == 3  # unknown values are ignored

    def test_deadline_and_posted_within(self, api_client, admin_user, category):
        from datetime import timedelta
        from django.utils import timezone

        now = timezone.now()
        _live(category, admin_user, title="Closes in 3 days", application_deadline=now + timedelta(days=3))
        _live(category, admin_user, title="Closes in 20 days", application_deadline=now + timedelta(days=20))
        _live(category, admin_user, title="Rolling")
        old = _live(category, admin_user, title="Posted long ago", application_deadline=now + timedelta(days=90))
        Opportunity.objects.filter(pk=old.pk).update(published_at=now - timedelta(days=40))

        assert self._titles(api_client, deadline="week") == ["Closes in 3 days"]
        assert self._titles(api_client, deadline="month") == ["Closes in 20 days", "Closes in 3 days"]
        assert self._titles(api_client, deadline="rolling") == ["Rolling"]
        assert "Posted long ago" not in self._titles(api_client, posted_within="30")
        assert len(self._titles(api_client, posted_within="0")) == 4  # out of range: ignored

    def test_location_terms_match_any(self, api_client, admin_user, category):
        _live(category, admin_user, title="Accra", location="Accra, Ghana (hybrid)")
        _live(category, admin_user, title="Nairobi", location="Nairobi, Kenya")
        _live(category, admin_user, title="Juba", location="Juba, South Sudan")

        assert self._titles(api_client, location="ghana") == ["Accra"]
        assert self._titles(api_client, location="Ghana, Kenya") == ["Accra", "Nairobi"]

    def test_duration_and_yes_no_filters(self, api_client, admin_user, category, owner):
        company = _company(owner, verified=True)
        _live(category, admin_user, title="3 months", role_type="internship", duration_months=3, accepts_minors=True)
        _live(category, admin_user, title="6 months", role_type="internship", duration_months=6)
        _live(category, admin_user, title="12 months", role_type="internship", duration_months=12,
              company=company, application_method="in_app")

        assert self._titles(api_client, duration="short") == ["3 months"]
        assert self._titles(api_client, duration="medium,long") == ["12 months", "6 months"]
        assert self._titles(api_client, apply_on_site="true") == ["12 months"]
        assert self._titles(api_client, verified="true") == ["12 months"]
        assert self._titles(api_client, open_to_minors="true") == ["3 months"]

    def test_several_categories(self, api_client, admin_user, category):
        from apps.opportunities.models import OpportunityCategory

        other = OpportunityCategory.objects.create(slug="health", name="Health")
        _live(category, admin_user, title="Job")
        _live(other, admin_user, title="Clinic")
        assert self._titles(api_client, category="jobs,health") == ["Clinic", "Job"]
        assert self._titles(api_client, category="health") == ["Clinic"]

    def test_locations_endpoint_counts_places(self, api_client, admin_user, category):
        from django.core.cache import cache

        cache.clear()
        _live(category, admin_user, title="a", location="Accra, Ghana (hybrid)")
        _live(category, admin_user, title="b", location="Tema, ghana")
        _live(category, admin_user, title="c", location="Remote")
        _live(category, admin_user, title="d", location="Oxford, UK", role_type="graduate_school")
        res = api_client.get("/api/opportunities/locations/")
        assert res.status_code == 200
        assert res.data == [{"name": "Ghana", "count": 2}, {"name": "Remote", "count": 1}]

    def test_employment_type_is_posted_by_companies(self, owner_client, owner, category):
        _company(owner, verified=True)
        res = owner_client.post("/api/companies/me/jobs/", _job_payload(category, employment_type="part_time"),
                                format="json")
        assert res.status_code == 201, res.data
        assert res.data["employment_type"] == "part_time"


class TestEmploymentTypeGuess:
    @pytest.mark.parametrize("text,expected", [
        ("Part-time research assistant", "part_time"),
        ("This is a full time role", "full_time"),
        ("Full-time or part-time", ""),
        ("Graduate trainee", ""),
    ])
    def test_guess(self, text, expected):
        from apps.ingestion.classify import employment_type

        assert employment_type(text) == expected
