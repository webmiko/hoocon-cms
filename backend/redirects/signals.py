"""Drop the in-memory redirect index whenever a Redirect row changes."""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from redirects.lookup import clear_redirect_index
from redirects.models import Redirect


@receiver(post_save, sender=Redirect, dispatch_uid="redirects_invalidate_on_save")
@receiver(post_delete, sender=Redirect, dispatch_uid="redirects_invalidate_on_delete")
def invalidate_redirect_index(**_kwargs: object) -> None:
    """Admin edits are visible immediately, not after the 60 s TTL."""
    clear_redirect_index()
