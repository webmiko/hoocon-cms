"""upload_product_image_package management command.

The command applies the scheme-audit upload package (manifest.json + files/)
to a target database: replaces broken wiring/dimensions bytes in place, adds
missing rows and unpublishes legacy combined schemes — with a strict dry-run
gate and a pre-write rollback snapshot.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from PIL import Image

from catalog.models import SKU, Category, Product, ProductImage

pytestmark = pytest.mark.django_db

WIRING_URL = "https://hoocon.ru/.local-assets/manuals-ru/da16mu-wiring.webp"
COMBINED_URL = "https://static.tildacdn.com/stor3866/10114942.jpg"


def _webp(color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="WEBP")
    return buf.getvalue()


def _make_sku(code: str) -> SKU:
    category = Category.objects.create(name="Приводы", slug=f"up-cat-{code.casefold()}")
    product = Product.objects.create(category=category, name=code, slug=f"up-product-{code.casefold()}")
    return SKU.objects.create(
        product=product,
        sku_code=code,
        name=code,
        slug=f"up-sku-{code.casefold()}",
        is_published=True,
    )


def _create_image(
    sku: SKU,
    *,
    filename: str,
    source_url: str,
    color: str = "blue",
    sort_order: int = 5,
    is_published: bool = True,
) -> ProductImage:
    return ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile(filename, _webp(color), content_type="image/webp"),
        alt=f"{sku.sku_code} alt",
        source_url=source_url,
        sort_order=sort_order,
        is_published=is_published,
    )


def _write_package(
    package_dir: Path,
    *,
    wiring_bytes: bytes,
    entries_replace: list[dict],
    entries_add: list[dict],
    entries_unpublish: list[dict],
    tamper: bool = False,
) -> Path:
    """Write a minimal upload package (manifest.json + files/) into package_dir."""
    files_dir = package_dir / "files"
    files_dir.mkdir(parents=True)
    payload = wiring_bytes + (b"x" if tamper else b"")
    (files_dir / "wiring.webp").write_bytes(payload)
    groups = []
    if entries_replace:
        groups.append(
            {
                "kind": "wiring",
                "action": "replace",
                "package_file": "files/wiring.webp",
                "sha256": hashlib.sha256(wiring_bytes).hexdigest(),
                "entries": entries_replace,
            },
        )
    if entries_add:
        groups.append(
            {
                "kind": "wiring",
                "action": "add",
                "package_file": "files/wiring.webp",
                "sha256": hashlib.sha256(wiring_bytes).hexdigest(),
                "entries": entries_add,
            },
        )
    if entries_unpublish:
        groups.append({"kind": "combined-legacy", "action": "unpublish", "entries": entries_unpublish})
    manifest = {"note": "test package", "groups": groups}
    (package_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return package_dir


def _entry(sku_code: str, source_url: str = WIRING_URL, sort_order: int = 5) -> dict:
    return {
        "sku_code": sku_code,
        "source_url": source_url,
        "target_filename": f"{sku_code.casefold()}-wiring.webp",
        "alt": f"{sku_code} | Схема подключения",
        "sort_order": sort_order,
    }


@pytest.fixture
def media_env(settings, tmp_path) -> Path:
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.PRIVATE_MEDIA_ROOT = str(tmp_path / "private_media")
    return tmp_path


def _run(cmd_args: list[str]) -> str:
    out = io.StringIO()
    call_command("upload_product_image_package", *cmd_args, stdout=out)
    return out.getvalue()


def test_dry_run_predicts_actions_and_writes_nothing(media_env: Path) -> None:
    sku_replace = _make_sku("DA16MU230-A")
    sku_add = _make_sku("DA16MQU230-A")
    existing = _create_image(sku_replace, filename="da16mu230-a-wiring.webp", source_url=WIRING_URL, color="blue")
    combined = _create_image(
        sku_add,
        filename="da16mqu230-a-combined.webp",
        source_url=COMBINED_URL,
        sort_order=2,
    )
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[_entry(sku_replace.sku_code)],
        entries_add=[_entry(sku_add.sku_code)],
        entries_unpublish=[{"sku_code": sku_add.sku_code, "source_url": COMBINED_URL, "alt": "legacy"}],
    )
    before = combined.is_published
    digest_before = hashlib.sha256(Path(existing.image.path).read_bytes()).hexdigest()

    output = _run(["--package-dir", str(package_dir), "--dry-run"])

    assert "update" in output and "create" in output and "unpublish" in output
    existing.refresh_from_db()
    combined.refresh_from_db()
    assert hashlib.sha256(Path(existing.image.path).read_bytes()).hexdigest() == digest_before
    assert combined.is_published == before
    assert not (package_dir / "rollback").exists()


def test_apply_replaces_in_place_creates_unpublishes_and_snapshots(media_env: Path) -> None:
    sku_replace = _make_sku("DA16MU230-A")
    sku_add = _make_sku("DA16MQU230-A")
    new_bytes = _webp("green")
    existing = _create_image(sku_replace, filename="da16mu230-a-wiring.webp", source_url=WIRING_URL, color="blue")
    old_bytes = Path(existing.image.path).read_bytes()
    old_path = existing.image.name
    combined = _create_image(
        sku_add,
        filename="da16mqu230-a-combined.webp",
        source_url=COMBINED_URL,
        sort_order=2,
    )
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=new_bytes,
        entries_replace=[_entry(sku_replace.sku_code)],
        entries_add=[_entry(sku_add.sku_code)],
        entries_unpublish=[{"sku_code": sku_add.sku_code, "source_url": COMBINED_URL, "alt": "legacy"}],
    )

    output = _run(["--package-dir", str(package_dir), "--yes"])

    existing.refresh_from_db()
    assert hashlib.sha256(Path(existing.image.path).read_bytes()).hexdigest() == hashlib.sha256(new_bytes).hexdigest()
    assert existing.sort_order == 5

    created = ProductImage.objects.get(sku=sku_add, source_url=WIRING_URL)
    assert created.is_published is True
    assert hashlib.sha256(Path(created.image.path).read_bytes()).hexdigest() == hashlib.sha256(new_bytes).hexdigest()

    combined.refresh_from_db()
    assert combined.is_published is False

    rollback_dirs = list((media_env / "private_media").glob("upload-rollback/upload-rollback-*"))
    assert len(rollback_dirs) == 1, output
    snapshot = json.loads((rollback_dirs[0] / "snapshot.json").read_text(encoding="utf-8"))
    rows = snapshot["rows"]
    replaced = next(r for r in rows if r["sku_code"] == sku_replace.sku_code and r["change"] == "update")
    assert replaced["image"] == old_path
    assert replaced["sha256"] == hashlib.sha256(old_bytes).hexdigest()
    backup_file = rollback_dirs[0] / replaced["file_backup"]
    assert backup_file.is_file()
    assert hashlib.sha256(backup_file.read_bytes()).hexdigest() == hashlib.sha256(old_bytes).hexdigest()
    unpublished = next(r for r in rows if r["change"] == "unpublish")
    assert unpublished["was_published"] is True
    creates = [r for r in rows if r["change"] == "create"]
    assert creates and creates[0]["sku_code"] == sku_add.sku_code


def test_gate_refuses_apply_when_replace_entry_would_create(media_env: Path) -> None:
    """A replace entry whose (sku, source_url) key is absent must stop the run.

    Otherwise upsert would insert a second gallery row next to the broken one —
    the duplication the whole gate exists to prevent.
    """
    sku = _make_sku("DA16MU230-A")
    _create_image(sku, filename="da16mu230-a-wiring-other.webp", source_url="https://other-key.webp", color="blue")
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[_entry(sku.sku_code)],
        entries_add=[],
        entries_unpublish=[],
    )

    with pytest.raises(CommandError):
        _run(["--package-dir", str(package_dir), "--yes"])
    assert ProductImage.objects.filter(sku=sku).count() == 1


def test_missing_sku_is_reported_and_blocks_apply(media_env: Path) -> None:
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[_entry("DA99MU230-A")],
        entries_add=[],
        entries_unpublish=[],
    )

    with pytest.raises(CommandError) as excinfo:
        _run(["--package-dir", str(package_dir), "--yes"])
    assert "DA99MU230-A" in str(excinfo.value)


def test_skip_entries_require_allow_skip_flag(media_env: Path) -> None:
    sku = _make_sku("DA16MU230-A")
    same_bytes = _webp("green")
    filename = "da16mu230-a-wiring.webp"
    ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile(filename, same_bytes, content_type="image/webp"),
        alt="DA16MU230-A | Схема подключения",
        source_url=WIRING_URL,
        sort_order=5,
        is_published=True,
    )
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=same_bytes,
        entries_replace=[_entry(sku.sku_code)],
        entries_add=[],
        entries_unpublish=[],
    )

    with pytest.raises(CommandError):
        _run(["--package-dir", str(package_dir), "--yes"])

    output = _run(["--package-dir", str(package_dir), "--yes", "--allow-skip"])
    assert "skip" in output


def test_locked_rows_block_apply(media_env: Path) -> None:
    """Locked rows are a hard anomaly: freeze ordering mistake, stop everything."""
    sku = _make_sku("DA16MU230-A")
    row = _create_image(sku, filename="da16mu230-a-wiring.webp", source_url=WIRING_URL, color="blue")
    ProductImage.objects.filter(pk=row.pk).update(image_locked=True)
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[_entry(sku.sku_code)],
        entries_add=[],
        entries_unpublish=[],
    )

    with pytest.raises(CommandError):
        _run(["--package-dir", str(package_dir), "--yes", "--allow-skip"])
    row.refresh_from_db()
    assert hashlib.sha256(Path(row.image.path).read_bytes()).hexdigest() != hashlib.sha256(_webp("green")).hexdigest()


def test_package_file_hash_mismatch_fails_before_db_writes(media_env: Path) -> None:
    sku = _make_sku("DA16MU230-A")
    _create_image(sku, filename="da16mu230-a-wiring.webp", source_url=WIRING_URL, color="blue")
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[_entry(sku.sku_code)],
        entries_add=[],
        entries_unpublish=[],
        tamper=True,
    )

    with pytest.raises(CommandError):
        _run(["--package-dir", str(package_dir), "--yes"])


def test_unpublish_already_unpublished_counts_as_skip(media_env: Path) -> None:
    sku = _make_sku("DA16MQU230-A")
    _create_image(
        sku,
        filename="da16mqu230-a-combined.webp",
        source_url=COMBINED_URL,
        sort_order=2,
        is_published=False,
    )
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[],
        entries_add=[_entry(sku.sku_code)],
        entries_unpublish=[{"sku_code": sku.sku_code, "source_url": COMBINED_URL, "alt": "legacy"}],
    )

    output = _run(["--package-dir", str(package_dir), "--yes", "--allow-skip"])
    assert "unpublish" in output


def test_second_run_after_successful_apply_is_idempotent(media_env: Path) -> None:
    sku = _make_sku("DA16MU230-A")
    _create_image(sku, filename="da16mu230-a-wiring.webp", source_url=WIRING_URL, color="blue")
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[_entry(sku.sku_code)],
        entries_add=[],
        entries_unpublish=[],
    )
    _run(["--package-dir", str(package_dir), "--yes"])
    shutil.rmtree(media_env / "private_media" / "upload-rollback")
    count_before = ProductImage.objects.filter(sku=sku).count()

    output = _run(["--package-dir", str(package_dir), "--yes", "--allow-skip"])

    assert ProductImage.objects.filter(sku=sku).count() == count_before
    assert "update=0" in output or "skip" in output


def test_expect_counts_mismatch_blocks_apply_before_writes(media_env: Path) -> None:
    """--expect-counts is the explicit first-run contract: 112/36/0 on prod.

    The check must fire before any write — a wrong package or wrong database
    stops the rollout, not after it already mutated rows.
    """
    sku = _make_sku("DA16MU230-A")
    row = _create_image(sku, filename="da16mu230-a-wiring.webp", source_url=WIRING_URL, color="blue")
    digest_before = hashlib.sha256(Path(row.image.path).read_bytes()).hexdigest()
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[_entry(sku.sku_code)],
        entries_add=[],
        entries_unpublish=[],
    )

    with pytest.raises(CommandError) as excinfo:
        _run(["--package-dir", str(package_dir), "--yes", "--expect-counts", "update=112,create=36"])
    assert "expect-counts" in str(excinfo.value)

    row.refresh_from_db()
    assert hashlib.sha256(Path(row.image.path).read_bytes()).hexdigest() == digest_before
    assert not (package_dir / "rollback").exists()

    output = _run(["--package-dir", str(package_dir), "--yes", "--expect-counts", "update=1,create=0"])
    assert "applied update=1" in output


def test_unpublish_sets_hidden_by_editor_so_etl_cannot_republish(media_env: Path) -> None:
    """Unpublished legacy rows must stay hidden: hidden_by_editor is the only
    durable unpublish in this codebase — bare is_published=False rows get
    re-published by ETL jobs and by upsert's unconditional is_published=True.
    """
    sku = _make_sku("DA16MQU230-A")
    combined = _create_image(
        sku,
        filename="da16mqu230-a-combined.webp",
        source_url=COMBINED_URL,
        sort_order=2,
    )
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[],
        entries_add=[_entry(sku.sku_code)],
        entries_unpublish=[{"sku_code": sku.sku_code, "source_url": COMBINED_URL, "alt": "legacy"}],
    )

    _run(["--package-dir", str(package_dir), "--yes"])

    combined.refresh_from_db()
    assert combined.is_published is False
    assert combined.hidden_by_editor is True


def test_gate_rejects_negative_sort_order_before_writes(media_env: Path) -> None:
    """A negative sort_order passes prediction but crashes full_clean mid-apply;
    the package must be rejected at load/gate time instead."""
    sku = _make_sku("DA16MU230-A")
    row = _create_image(sku, filename="da16mu230-a-wiring.webp", source_url=WIRING_URL, color="blue")
    digest_before = hashlib.sha256(Path(row.image.path).read_bytes()).hexdigest()
    package_dir = media_env / "package"
    bad_entry = _entry(sku.sku_code)
    bad_entry["sort_order"] = -5
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[bad_entry],
        entries_add=[],
        entries_unpublish=[],
    )

    with pytest.raises(CommandError):
        _run(["--package-dir", str(package_dir), "--yes"])
    row.refresh_from_db()
    assert hashlib.sha256(Path(row.image.path).read_bytes()).hexdigest() == digest_before


def test_gate_rejects_corrupt_webp_bytes(media_env: Path) -> None:
    """Bytes with valid magic but broken payload are published without a card;
    validate decodability at gate, not after rows are written."""
    sku = _make_sku("DA16MU230-A")
    _create_image(sku, filename="da16mu230-a-wiring.webp", source_url=WIRING_URL, color="blue")
    package_dir = media_env / "package"
    corrupt = _webp("green")[:20]  # обрезанный webp — magic есть, payload нет
    _write_package(
        package_dir,
        wiring_bytes=corrupt,
        entries_replace=[_entry(sku.sku_code)],
        entries_add=[],
        entries_unpublish=[],
    )

    with pytest.raises(CommandError):
        _run(["--package-dir", str(package_dir), "--yes"])


def test_package_file_path_traversal_rejected(media_env: Path) -> None:
    """package_file must stay inside the package: sha256 is self-declared by the
    same manifest, so `../` or absolute paths would smuggle arbitrary host files."""
    package_dir = media_env / "package"
    files_dir = package_dir / "files"
    files_dir.mkdir(parents=True)
    outside = media_env / "outside.webp"
    outside.write_bytes(_webp("green"))
    manifest = {
        "groups": [
            {
                "kind": "wiring",
                "action": "replace",
                "package_file": "../outside.webp",
                "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                "entries": [_entry("DA16MU230-A")],
            },
        ],
    }
    (package_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CommandError):
        _run(["--package-dir", str(package_dir), "--yes"])


def test_rollback_snapshot_defaults_to_private_media(media_env: Path) -> None:
    """The rollback copy is the ONLY pre-upload byte copy (old files are deleted
    by media hygiene); inside a container the package dir is ephemeral — the
    default must be the persistent private_media volume."""
    sku = _make_sku("DA16MU230-A")
    _create_image(sku, filename="da16mu230-a-wiring.webp", source_url=WIRING_URL, color="blue")
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[_entry(sku.sku_code)],
        entries_add=[],
        entries_unpublish=[],
    )

    _run(["--package-dir", str(package_dir), "--yes"])

    private_rollbacks = list((media_env / "private_media").glob("upload-rollback/upload-rollback-*/snapshot.json"))
    assert private_rollbacks, "rollback snapshot must default into PRIVATE_MEDIA_ROOT"
    assert not (package_dir / "rollback").exists()


def test_unpublish_with_missing_file_does_not_block_apply(media_env: Path) -> None:
    """Unpublish changes no bytes — a missing file on such a row must not
    hard-block the rollout; no byte backup is needed for rows we do not rewrite."""
    sku = _make_sku("DA16MQU230-A")
    combined = _create_image(
        sku,
        filename="da16mqu230-a-combined.webp",
        source_url=COMBINED_URL,
        sort_order=2,
    )
    Path(combined.image.path).unlink()  # файл потерян — байты всё равно не меняем
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[],
        entries_add=[_entry(sku.sku_code)],
        entries_unpublish=[{"sku_code": sku.sku_code, "source_url": COMBINED_URL, "alt": "legacy"}],
    )

    output = _run(["--package-dir", str(package_dir), "--yes"])

    combined.refresh_from_db()
    assert combined.is_published is False
    assert "unpublish" in output


def test_unpublish_applies_after_upserts_regardless_of_manifest_order(media_env: Path) -> None:
    """Two-phase apply: even when the manifest lists unpublish first, all upserts
    must land before any unpublish — a mid-apply crash can never leave a SKU
    with no published schemes."""
    sku = _make_sku("DA16MQU230-A")
    combined = _create_image(
        sku,
        filename="da16mqu230-a-combined.webp",
        source_url=COMBINED_URL,
        sort_order=2,
    )
    package_dir = media_env / "package"
    files_dir = package_dir / "files"
    files_dir.mkdir(parents=True)
    payload = _webp("green")
    (files_dir / "da16mqu230-a-wiring.webp").write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()
    # unpublish-группа намеренно ПЕРВАЯ в манифесте
    manifest = {
        "groups": [
            {
                "kind": "combined-legacy",
                "action": "unpublish",
                "entries": [{"sku_code": sku.sku_code, "source_url": COMBINED_URL, "alt": "legacy"}],
            },
            {
                "kind": "wiring",
                "action": "add",
                "package_file": "files/da16mqu230-a-wiring.webp",
                "sha256": sha,
                "entries": [_entry(sku.sku_code)],
            },
        ],
    }
    (package_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    _run(["--package-dir", str(package_dir), "--yes"])

    combined.refresh_from_db()
    assert combined.is_published is False
    wiring = ProductImage.objects.get(sku=sku, source_url=WIRING_URL)
    assert wiring.is_published is True


def test_replace_with_missing_file_is_repaired_not_blocked(media_env: Path) -> None:
    """A replace row whose file is already lost has nothing to back up — the
    upload IS the repair. Snapshot records empty backup and apply proceeds."""
    sku = _make_sku("DA16MU230-A")
    row = _create_image(sku, filename="da16mu230-a-wiring.webp", source_url=WIRING_URL, color="blue")
    Path(row.image.path).unlink()
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[_entry(sku.sku_code)],
        entries_add=[],
        entries_unpublish=[],
    )

    _run(["--package-dir", str(package_dir), "--yes"])

    row.refresh_from_db()
    assert hashlib.sha256(Path(row.image.path).read_bytes()).hexdigest() == hashlib.sha256(_webp("green")).hexdigest()


def test_malformed_expect_counts_is_an_error_not_silent_pass(media_env: Path) -> None:
    """A typo in --expect-counts must fail loudly; silently dropping the part
    would remove the contract the operator thinks is active."""
    sku = _make_sku("DA16MU230-A")
    _create_image(sku, filename="da16mu230-a-wiring.webp", source_url=WIRING_URL, color="blue")
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[_entry(sku.sku_code)],
        entries_add=[],
        entries_unpublish=[],
    )

    with pytest.raises(CommandError):
        _run(["--package-dir", str(package_dir), "--yes", "--expect-counts", "update=abc"])


def test_output_prints_package_manifest_sha256(media_env: Path) -> None:
    """Both dry-run and apply print the manifest hash so the operator can verify
    they are looking at the same package they reviewed."""
    sku = _make_sku("DA16MU230-A")
    _create_image(sku, filename="da16mu230-a-wiring.webp", source_url=WIRING_URL, color="blue")
    package_dir = media_env / "package"
    _write_package(
        package_dir,
        wiring_bytes=_webp("green"),
        entries_replace=[_entry(sku.sku_code)],
        entries_add=[],
        entries_unpublish=[],
    )
    expected = hashlib.sha256((package_dir / "manifest.json").read_bytes()).hexdigest()

    output = _run(["--package-dir", str(package_dir)])

    assert f"package sha256: {expected}" in output
