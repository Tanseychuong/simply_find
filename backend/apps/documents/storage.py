"""Private storage for personal documents (settings.STORAGES['applications']):
vault documents and the copies attached to applications. Never the public
media bucket; files leave it only through signed-in download views."""

import uuid
from pathlib import Path

from django.core.files.storage import storages
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils.functional import LazyObject, empty


class _PrivateStorage(LazyObject):
    """Resolved on first use, not at import: Django evaluates a field's
    storage callable once when models load, which would pin whatever
    STORAGES said at that moment (and ignore test or runtime overrides)."""

    def _setup(self):
        self._wrapped = storages["applications"]


private_files_storage = _PrivateStorage()


@receiver(setting_changed)
def _reset_private_storage(*, setting, **kwargs):
    if setting == "STORAGES":
        private_files_storage._wrapped = empty


def private_storage():
    return private_files_storage


def unguessable_name(folder: str, filename: str) -> str:
    return f"{folder}/{uuid.uuid4().hex}{Path(filename).suffix.lower()[:10]}"
