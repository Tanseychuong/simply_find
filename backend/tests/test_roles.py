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
