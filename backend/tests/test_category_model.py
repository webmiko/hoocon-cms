"""Tests for catalog.Category model (TDD: red → green → refactor).

Spec: ПЛАН §6 Iter 1; docs/readiness-backend-ux.md §2.2 —
Category(self-ref tree, slug unique). Категории по применению:
воздух / ПБ / дым / краны. slug = path-сегмент (напр. `vozdushnie`).
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError


@pytest.mark.django_db
def test_create_category_with_name_and_slug() -> None:
    """Can create a root category with name and slug."""
    from catalog.models import Category

    category = Category.objects.create(
        name="Воздушные приводы",
        slug="vozdushnie",
    )
    assert category.pk is not None
    assert category.name == "Воздушные приводы"
    assert category.slug == "vozdushnie"


@pytest.mark.django_db
def test_slug_must_be_unique() -> None:
    """Duplicate slug raises IntegrityError (URL path collision)."""
    from catalog.models import Category

    Category.objects.create(name="A", slug="dup")
    with pytest.raises(IntegrityError):
        Category.objects.create(name="B", slug="dup")


@pytest.mark.django_db
def test_parent_can_be_null_for_root_category() -> None:
    """Root category has no parent (tree top level)."""
    from catalog.models import Category

    root = Category.objects.create(name="Root", slug="root")
    assert root.parent is None


@pytest.mark.django_db
def test_category_can_have_child() -> None:
    """Self-referential FK: a category can have a parent."""
    from catalog.models import Category

    parent = Category.objects.create(name="Приводы", slug="privody")
    child = Category.objects.create(
        name="Воздушные",
        slug="vozdushnie",
        parent=parent,
    )
    assert child.parent_id == parent.pk
    assert child.parent == parent


@pytest.mark.django_db
def test_str_returns_name() -> None:
    """__str__ returns the human-readable name (for Admin)."""
    from catalog.models import Category

    category = Category.objects.create(name="Краны", slug="krany")
    assert str(category) == "Краны"


@pytest.mark.django_db
def test_description_is_optional() -> None:
    """Description can be empty (not all categories need long text)."""
    from catalog.models import Category

    category = Category.objects.create(name="X", slug="x")
    assert category.description == ""
