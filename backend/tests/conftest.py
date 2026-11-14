"""
Shared fixtures. One user fixture per access tier (user/moderator/admin)
so tests read as "given a <tier> user" rather than constructing users
inline everywhere, and a change to how a tier is granted only needs
updating here.
"""

import pytest
from django.contrib.auth.models import Permission
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.opportunities.models import OpportunityCategory


@pytest.fixture(autouse=True)
def _reset_throttles():
    # Throttle counters live in the cache; without this, login/register
    # calls from earlier tests count against later ones.
    cache.clear()


@pytest.fixture(autouse=True)
def _fast_password_hashing(settings):
    # Real hashers are deliberately slow (~1s per user on this machine);
    # tests create many users. Django's docs recommend this for test runs.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def _local_file_storage(settings, tmp_path):
    # The developer shell may export production Supabase storage keys; tests
    # must never upload to (or read from) a real bucket.
    fs = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.STORAGES = {**settings.STORAGES, "default": fs, "applications": fs}


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def category(db):
    return OpportunityCategory.objects.create(slug="jobs", name="Jobs & Internships")


@pytest.fixture
def user(db):
    return User.objects.create_user(email="user@example.com", name="Test User", password="testpass123")


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(email="admin@example.com", name="Admin", password="testpass123")


@pytest.fixture
def moderator_user(db):
    user = User.objects.create_user(
        email="mod@example.com", name="Moderator", password="testpass123", is_staff=True,
    )
    permission = Permission.objects.get(codename="can_verify_opportunity")
    user.user_permissions.add(permission)
    return user
