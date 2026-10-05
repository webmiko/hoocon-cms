"""Tests for prune_dead_media: dead files quarantined, referenced kept.

Django never deletes storage files on row delete/re-upload, so ETL
iterations pile up orphans under MEDIA_ROOT — this command is the broom.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.core.management.base import CommandError

from catalog.media_hygiene import audit_dead_media, list_quarantine_batches
from content.models import Article


def _touch(root: Path, rel: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


@pytest.mark.django_db
def test_audit_flags_dead_missing_and_skips_pack(tmp_path: Path) -> None:
    """Unreferenced file is dead; FileField value and _pack staging are not."""
    article = Article.objects.create(
        title="a",
        slug="a",
        body='<img src="/media/article_inline/x/inline.webp">',
        cover="article_covers/a/live.webp",
        cover_dark="article_covers/a/gone.webp",
    )
    assert article.pk
    _touch(tmp_path, "article_covers/a/live.webp")
    _touch(tmp_path, "article_covers/a/dead.webp")
    _touch(tmp_path, "article_inline/x/inline.webp")
    _touch(tmp_path, "_pack/pack.bin")

    report = audit_dead_media(tmp_path)

    assert "article_covers/a/dead.webp" in report["dead"]
    assert "article_covers/a/live.webp" not in report["dead"]
    assert "article_inline/x/inline.webp" not in report["dead"]  # body URL keeps it alive
    assert "_pack/pack.bin" not in report["dead"]  # ETL staging never scanned
    assert "article_covers/a/gone.webp" in report["missing"]  # DB ref without file


@pytest.mark.django_db
def test_audit_fixture_refs_keep_files_alive(tmp_path: Path) -> None:
    """A file referenced only by a repo fixture is not dead (re-import source)."""
    media_root = tmp_path / "media"
    _touch(media_root, "article_inline/legacy/from-fixture.webp")
    fixture = tmp_path / "repo" / "content" / "fixtures" / "page.html"
    fixture.parent.mkdir(parents=True)
    fixture.write_text('<img src="/media/article_inline/legacy/from-fixture.webp">', encoding="utf-8")

    report = audit_dead_media(media_root, repo_root=tmp_path / "repo")

    assert "article_inline/legacy/from-fixture.webp" not in report["dead"]


@pytest.mark.django_db
def test_audit_include_pack_marks_staging_dead(tmp_path: Path) -> None:
    """--include-pack opts _pack files into the dead scan."""
    _touch(tmp_path, "_pack/pack.bin")
    assert "_pack/pack.bin" in audit_dead_media(tmp_path, include_pack=True)["dead"]


@pytest.mark.django_db
def test_command_dry_run_reports_without_moving(tmp_path: Path) -> None:
    """Default run prints stats but leaves every file in place."""
    _touch(tmp_path, "news_covers/n/dead.webp")
    out = io.StringIO()

    call_command("prune_dead_media", media_root=str(tmp_path), stdout=out)

    assert "dead (no reference): 1 files" in out.getvalue()
    assert "dry-run" in out.getvalue()
    assert (tmp_path / "news_covers/n/dead.webp").is_file()


@pytest.mark.django_db
def test_command_apply_quarantines_dead_with_manifest(tmp_path: Path) -> None:
    """--apply moves dead files to _quarantine/<stamp>/, keeps referenced."""
    Article.objects.create(title="a", slug="a", cover="article_covers/a/live.webp")
    _touch(tmp_path, "article_covers/a/live.webp")
    _touch(tmp_path, "article_covers/a/dead.webp")
    out = io.StringIO()

    call_command("prune_dead_media", apply=True, media_root=str(tmp_path), stdout=out)

    assert (tmp_path / "article_covers/a/live.webp").is_file()
    assert not (tmp_path / "article_covers/a/dead.webp").exists()
    batches = list_quarantine_batches(tmp_path)
    assert len(batches) == 1
    batch = tmp_path / "_quarantine" / batches[0]
    assert (batch / "article_covers/a/dead.webp").is_file()
    assert "article_covers/a/dead.webp" in (batch / "manifest.txt").read_text()


@pytest.mark.django_db
def test_command_purge_removes_batch(tmp_path: Path) -> None:
    """--purge deletes a named quarantine batch; unsafe names rejected."""
    _touch(tmp_path, "gone/dead.webp")
    call_command("prune_dead_media", apply=True, media_root=str(tmp_path), stdout=io.StringIO())
    batch = list_quarantine_batches(tmp_path)[0]
    out = io.StringIO()

    call_command("prune_dead_media", purge=batch, yes=True, media_root=str(tmp_path), stdout=out)

    assert "purged" in out.getvalue()
    assert not (tmp_path / "_quarantine" / batch).exists()
    with pytest.raises(CommandError):
        call_command("prune_dead_media", purge="../gone", yes=True, media_root=str(tmp_path))


def _tmp_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field_name: str) -> None:
    """Point an Article file field at a tmp storage so deletes stay sandboxed."""
    field = Article._meta.get_field(field_name)
    monkeypatch.setattr(field, "storage", FileSystemStorage(location=str(tmp_path)))


@pytest.mark.django_db
def test_row_delete_removes_file_from_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """post_delete frees the file — this is what stops orphans accumulating."""
    _tmp_storage(tmp_path, monkeypatch, "cover")
    path = _touch(tmp_path, "article_covers/t/gone.webp")
    article = Article.objects.create(title="a", slug="a", cover="article_covers/t/gone.webp")

    article.delete()

    assert not path.exists()


@pytest.mark.django_db
def test_row_delete_keeps_file_shared_by_other_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A file referenced by a second row survives until that row is gone too."""
    _tmp_storage(tmp_path, monkeypatch, "cover")
    path = _touch(tmp_path, "article_covers/t/shared.webp")
    a = Article.objects.create(title="a", slug="a", cover="article_covers/t/shared.webp")
    b = Article.objects.create(title="b", slug="b", cover="article_covers/t/shared.webp")

    a.delete()
    assert path.exists()
    b.delete()
    assert not path.exists()


@pytest.mark.django_db
def test_file_replace_deletes_old_after_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: Any,
) -> None:
    """pre_save + on_commit: re-uploading a field drops the replaced file."""
    _tmp_storage(tmp_path, monkeypatch, "cover")
    old_path = _touch(tmp_path, "article_covers/t/old.webp")
    article = Article.objects.create(title="a", slug="a", cover="article_covers/t/old.webp")

    with django_capture_on_commit_callbacks(execute=True):
        article.cover = "article_covers/t/new.webp"
        article.save()

    assert not old_path.exists()
