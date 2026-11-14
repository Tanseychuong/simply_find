"""Stored files are not removed by Django when their row is deleted, so a
deleted account (which cascades to its applications) would otherwise leave
CVs behind in storage. Remove the file with the row."""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ApplicationAnswer


@receiver(post_delete, sender=ApplicationAnswer)
def delete_answer_file(sender, instance, **kwargs):
    if instance.file:
        name, storage = instance.file.name, instance.file.storage
        # After commit, so a rolled-back delete never loses a file.
        transaction.on_commit(lambda: storage.delete(name))
