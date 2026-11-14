"""The guided profile: four steps, what each still needs, and a score."""

from apps.documents.models import Credential, Document

STEPS = [
    ("about", "About you"),
    ("studies", "Your studies"),
    ("skills", "Your skills"),
    ("documents", "Documents and certificates"),
]

LABELS = {
    "name": "your name",
    "date_of_birth": "date of birth",
    "country": "country",
    "status": "student or graduate",
    "institution": "school or university",
    "programme": "course or programme",
    "graduation_year": "graduation year",
    "skills": "at least one skill",
    "documents": "a document or certificate",
}


def _missing(profile, step: str) -> list[str]:
    user = profile.user
    if step == "about":
        checks = {"name": user.name, "date_of_birth": profile.date_of_birth, "country": profile.country}
    elif step == "studies":
        checks = {"status": profile.status, "institution": profile.institution,
                  "programme": profile.programme, "graduation_year": profile.graduation_year}
    elif step == "skills":
        checks = {"skills": profile.skills}
    else:
        has_any = (Document.objects.filter(owner=user).exists()
                   or Credential.objects.filter(owner=user).exists())
        checks = {"documents": has_any}
    return [key for key, value in checks.items() if not value]


def progress(profile) -> dict:
    steps, total, done = [], 0, 0
    for key, label in STEPS:
        missing = _missing(profile, key)
        size = {"about": 3, "studies": 4, "skills": 1, "documents": 1}[key]
        total += size
        done += size - len(missing)
        steps.append({"key": key, "label": label, "done": not missing,
                      "missing": [{"field": m, "label": LABELS[m]} for m in missing]})
    next_step = next((s["key"] for s in steps if not s["done"]), None)
    return {"steps": steps, "completeness": round(100 * done / total), "next_step": next_step}


def ready_to_apply(profile) -> list[str]:
    """What's still missing before applying (the first two steps)."""
    return [LABELS[m] for step in ("about", "studies") for m in _missing(profile, step)]
