"""Remove a vault file from storage with its row (also when an account is deleted)."""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Document


@receiver(post_delete, sender=Document)
def delete_document_file(sender, instance, **kwargs):
    if instance.file:
        name, storage = instance.file.name, instance.file.storage
        transaction.on_commit(lambda: storage.delete(name))
