"""Settings as production loads them (DEBUG off). Settings are read once at
import, so each case runs in a fresh interpreter with a production-like
environment."""

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

PRODUCTION_ENV = {
    "DEBUG": "False",
    "SECRET_KEY": "test-only-production-like-secret-0123456789",
    "SITE_URL": "https://simplyfind.example",
    "DATABASE_URL": "postgres://u:p@localhost:5432/d",
    "SUPABASE_URL": "https://project.supabase.co",
    "SUPABASE_STORAGE_BUCKET": "public",
    "SUPABASE_PRIVATE_BUCKET": "private",
    "SUPABASE_S3_ACCESS_KEY_ID": "key",
    "SUPABASE_S3_SECRET_ACCESS_KEY": "secret",
}


def _settings(**extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CSRF_TRUSTED_ORIGINS", "CORS_ALLOWED_ORIGINS", "FRONTEND_URL", "DJANGO_SETTINGS_MODULE")}
    env.update(PRODUCTION_ENV, **extra)
    code = (
        "import json, django; from django.conf import settings; "
        "print(json.dumps({'csrf': settings.CSRF_TRUSTED_ORIGINS, 'cors': settings.CORS_ALLOWED_ORIGINS}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", f"import os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; {code}"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_website_is_a_trusted_csrf_origin_in_production():
    # Signed-in POSTs from the website carry its Origin; without it here,
    # every signed-in write in production failed with "CSRF failed".
    s = _settings()
    assert "https://simplyfind.example" in s["csrf"]


def test_extra_csrf_origins_add_to_the_website_rather_than_replace_it():
    s = _settings(CSRF_TRUSTED_ORIGINS="https://api.simplyfind.example",
                  CORS_ALLOWED_ORIGINS="https://www.simplyfind.example")
    assert s["csrf"] == ["https://simplyfind.example", "https://www.simplyfind.example",
                         "https://api.simplyfind.example"]
    assert "http://localhost:5173" not in s["cors"]  # dev origins only with DEBUG on
