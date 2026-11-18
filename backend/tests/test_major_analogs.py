"""Tests for curated major-brand analogs (gap products).

Политика: во вкладке «Аналоги» больше нет буллетов «– Марка АРТИКУЛ» —
совпадение по моменту/площади не доказывает замену конкретной модели.
Генераторы пишут только заголовок серии, методичку по классу и футер-
инструкцию подбора. Буллет вернётся, когда пара будет сверена с даташитом.
"""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_damu_analogs import build_damu_analogs
from catalog.etl.series_copy_major_analogs import (
    analogs_text_for_product,
    apply_major_analogs_enrichment,
    build_damqu_analogs,
    build_hva_analogs,
    build_hvd_air_analogs,
    build_qx_analogs,
    build_sa7mu_analogs,
)
from catalog.etl.series_copy_spring_analogs import (
    build_dafu_analogs,
    build_safu_analogs,
    build_samu_analogs,
)
from catalog.models import SKU, Category, Product


def _all_analog_builders() -> list[tuple[str, str]]:
    """(builder-name, generated text) across every analog copy generator."""
    texts: list[tuple[str, str]] = []
    for nm in (2, 4, 6, 8, 16, 24, 32):
        texts.append((f"build_damu_analogs({nm})", build_damu_analogs(nm)))
    for nm in (5, 8, 10, 16, 20, 24, 40):
        texts.append((f"build_damqu_analogs({nm})", build_damqu_analogs(nm)))
    texts.append(("build_sa7mu_analogs()", build_sa7mu_analogs()))
    for nm in (10, 15, 30):
        texts.append((f"build_samu_analogs({nm})", build_samu_analogs(nm)))
    for nm in (3, 5, 10, 15, 20):
        texts.append((f"build_dafu_analogs({nm})", build_dafu_analogs(nm)))
        texts.append((f"build_safu_analogs({nm})", build_safu_analogs(nm)))
    for nm in (5, 10, 20, 40):
        for fast in (False, True):
            texts.append((f"build_hva_analogs({nm}, fast={fast})", build_hva_analogs(nm, fast=fast)))
            texts.append((f"build_hvd_air_analogs({nm}, fast={fast})", build_hvd_air_analogs(nm, fast=fast)))
        for brand in ("HVA", "HVD"):
            texts.append((f"build_qx_analogs({brand}, {nm})", build_qx_analogs(brand, nm)))
    return texts


def test_generated_analogs_have_no_foreign_article_bullets() -> None:
    """Ни один генератор не пишет буллет «– Марка АРТИКУЛ» и заголовки исполнений."""
    for name, text in _all_analog_builders():
        assert "– " not in text, name
        for banned in ("Аналоги для ", "(24 В,", "(230 В,"):
            assert banned not in text, name


def test_generated_analogs_keep_guidance_and_footnote() -> None:
    """Каждый текст держит заголовок серии и футер-инструкцию подбора."""
    for name, text in _all_analog_builders():
        assert text.startswith("Список аналогов"), name
        assert "сверяйте крутящий момент" in text, name
        assert "паспорту / шильдику" in text, name


def test_build_damu_analogs_belimo_bands() -> None:
    """DAMU copy names the class band; no edition blocks, no Belimo article."""
    d16 = build_damu_analogs(16)
    assert "DA16MU24-D" not in d16
    assert "Belimo NM24A" not in d16
    assert "16 Нм" in d16.splitlines()[0]
    d24 = build_damu_analogs(24)
    assert "DA.MU 16 Нм" not in d24
    assert "24 Нм" in d24.splitlines()[0]
    assert "Belimo SM24A" not in d24
    d6 = build_damu_analogs(6)
    assert "Belimo LM24A" not in d6
    d32 = build_damu_analogs(32)
    assert "Belimo SM24A" not in d32
    d2 = build_damu_analogs(2)
    assert "Belimo TMC" not in d2
    # DA2MU data file: старые буллеты-клоны и Siemens-строки вычищены.
    for banned in ("Dastech", "Lufberg", "Sputnik", "BVM", "Siemens GSD", "– "):
        assert banned not in d2


def test_build_samu_analogs_no_emf_or_cm() -> None:
    """SA smoke: нет Belimo-статей, нет CM, нет буллетов других марок."""
    sa10 = build_samu_analogs(10)
    assert "Belimo" not in sa10.split("Крупные марки")[0]
    assert "EMF" not in sa10
    assert "CM24" not in sa10
    assert "GIB" not in sa10
    sa15 = build_samu_analogs(15)
    assert "Belimo BEN24" not in sa15
    assert "Belimo BEN230" not in sa15
    assert "BLE" not in sa15
    assert "BEN24-T" not in sa15
    assert "BEN230-T" not in sa15


def test_build_dafu_safu_belimo_families() -> None:
    """DAFU/SAFU: каталожная полоса в методичке, статей и FST/FSR-3N нет."""
    da15 = build_dafu_analogs(15)
    assert "Belimo NF24A" not in da15
    assert "GCA" not in da15
    assert "GDB" not in da15
    assert "BX24" not in da15
    sa20 = build_safu_analogs(20)
    assert "Belimo BF24" not in sa20
    assert "Gruner 340" not in sa20
    assert "BFL24-20" not in sa20
    assert "BLF230-20" not in sa20
    # FST-24-3N / FSR-230-3N are not Belimo articles (US series is FSTF/FSNF).
    sa3 = build_safu_analogs(3)
    assert "FST-" not in sa3
    assert "FSR-" not in sa3


def test_build_damqu_analogs_no_articles_or_clones() -> None:
    """DAMQU copy keeps the major-brands line and prints no articles/clones."""
    text = build_damqu_analogs(5)
    assert "DA5MQU24-DS" not in text
    assert "Belimo LMQ" not in text
    assert "Siemens" in text  # строка крупных марок, не буллет-статья
    assert "Honeywell" in text
    for ban in ("Nanotek", "Dastech", "Lufberg", "BVM", "Sputnik"):
        assert ban not in text


def test_build_damqu_analogs_distinct_belimo_by_nm() -> None:
    """Q-полоса по площади: 5 → LMQ (0.5≥0.4), 8 → NMQ (0.8≥0.8), 16 → SMQ (1.6≥1.6)."""
    from catalog.etl.belimo_analogs import belimo_family_by_area

    assert belimo_family_by_area("fast", 0.4) == "LMQ"
    assert belimo_family_by_area("fast", 0.5) == "LMQ"
    assert belimo_family_by_area("fast", 0.8) == "NMQ"
    assert belimo_family_by_area("fast", 1.0) == "NMQ"
    assert belimo_family_by_area("fast", 1.6) == "SMQ"
    assert belimo_family_by_area("fast", 2.4) == "SMQ"
    assert belimo_family_by_area("fast", 4.0) == "GMQ"
    assert "Belimo SMQ" not in build_damqu_analogs(16)
    assert "Belimo SMQ" not in build_damqu_analogs(24)


def test_qx_analogs_keep_electronic_return_only() -> None:
    """QX не получает LMQ…GMQ, пружинный GCA и MN6105 без возврата.

    Belimo fast brochure 2026: LMQ/NMQ/SMQ — non fail-safe.
    Siemens HIT: GCA161.1E — 18 Nm, spring return, AC/DC 24 V.
    Honeywell 63-1313: MN6105 — non-spring return, 24 V.
    SuperCap NKQ is 6 Nm / 1.2 m², 24 V only (fail-safe brochure 2026),
    so 5 and 10 Nm have no direct article and 20/40 Nm 24 V do.
    """
    for brand in ("HVA", "HVD"):
        for nm in (5, 10, 20, 40):
            text = build_qx_analogs(brand, nm)
            for banned in ("LMQ", "NMQ", "SMQ", "GMQ", "GCA", "MN6105"):
                assert banned not in text, (brand, nm, banned)
    hva20 = build_qx_analogs("HVA", 20)
    assert "NKQ" not in hva20
    assert "GK" not in hva20
    assert "Belimo NKQ" not in build_qx_analogs("HVD", 20)
    # 230 V non-spring guidance stays class-level: no generated Siemens article.
    plain = build_hva_analogs(5, fast=False)
    assert "Siemens GDB361.1E" not in plain
    assert "GCA" not in plain
    fast = build_hva_analogs(5, fast=True)
    assert "Belimo LMQ" not in fast
    assert "Siemens GDB361.1E" not in fast
    assert "Siemens GLB361.1E" not in build_hva_analogs(10, fast=False)


def test_siemens_articles_are_not_synthesized() -> None:
    """Ни один генератор не склеивает Siemens-артикулы по шаблону.

    Раньше …31x/.1E и …61x/.1E собирались из напряжения/управления и
    доклеивался суффикс -S концевика — таких пар в даташитах нет.
    """
    for name, text in _all_analog_builders():
        for banned in (
            "GDB1",
            "GDB3",
            "GLB1",
            "GLB3",
            "GEB1",
            "GEB3",
            "GIB1",
            "GIB3",
            "GCA1",
            ".1E-S",
        ):
            assert banned not in text, name


def test_build_sa7mu_and_hvd_have_no_articles() -> None:
    """SA7 smoke и HVD air: ни Belimo-, ни Siemens-/JCI-статей в тексте."""
    sa = build_sa7mu_analogs()
    assert "SA7MU24-DST" not in sa
    assert "Belimo" not in sa
    assert "GIB161.1E" not in sa
    assert "Nanotek" not in sa
    hvd = build_hvd_air_analogs(40, fast=False)
    assert "HVD24-40" not in hvd
    assert "Belimo GM24A" not in hvd
    assert "Johnson Controls M9" not in hvd


@pytest.mark.django_db
def test_apply_major_analogs_fills_empty_only() -> None:
    """Empty product gets curated text; filled product is skipped without force."""
    cat = Category.objects.create(name="Air", slug="air-major-analog")
    empty = Product.objects.create(
        name="DA5MQU",
        slug="privod-vozdushniy-da5mqu-5nm",
        category=cat,
        analogs_text="",
    )
    SKU.objects.create(
        product=empty,
        sku_code="DA5MQU24-DS",
        slug="da5mqu24-ds-major",
        name="DA5MQU24-DS",
    )
    filled = Product.objects.create(
        name="HVA-5",
        slug="privod-vozdushniy-hva-5nm",
        category=cat,
        analogs_text="Already has Belimo BM24-5-05",
    )
    stats = apply_major_analogs_enrichment(dry_run=False, force=False)
    empty.refresh_from_db()
    filled.refresh_from_db()
    assert empty.pk in [Product.objects.get(slug=s).pk for s in stats["slugs"]] or empty.slug in stats["slugs"]
    assert "Belimo" in (empty.analogs_text or "")
    assert filled.analogs_text == "Already has Belimo BM24-5-05"
    assert analogs_text_for_product(empty)
    sku = SKU.objects.get(sku_code="DA5MQU24-DS")
    assert "Belimo" in (sku.analogs_text or "")
