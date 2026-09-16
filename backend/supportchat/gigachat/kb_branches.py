"""Structured branches in ``gigachat_kb.txt`` — smart search for the bot."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

from supportchat.gigachat.kb_text import PACKAGED_KB_PATH, _append_wrapped_lines
from supportchat.gigachat.manuals_kb import extract_sku_tokens, extract_voltage_hint

KB_FORMAT_VERSION = 2
_POLICY_BRANCH_ID = "policy.bot"
_INDEX_BRANCH_ID = "nav.index"

_BRANCH_BEGIN_RE = re.compile(r"^@BRANCH\s+BEGIN\s+(.+)$")
_BRANCH_ATTR_RE = re.compile(
    r"(id|tags|series|tokens)=([^\s].*?)(?=\s+(?:id|tags|series|tokens)=|$)",
)


def _parse_branch_begin_attrs(raw: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _BRANCH_ATTR_RE.finditer(raw.strip()):
        attrs[match.group(1)] = match.group(2).strip()
    return attrs


_BRANCH_END_RE = re.compile(r"^@BRANCH\s+END\s*$")
_META_RE = re.compile(r"^@META\s+version=(\d+)\s+built_at=([^\s]+)\s+branches=(\d+)\s*$")
_TITLE_RE = re.compile(r"^@TITLE\s+(.+)$")
_GOTO_RE = re.compile(r"^@GOTO\s+(.+?)\s*→\s*(.+?)\s*$")


@dataclass(frozen=True, slots=True)
class KbBranch:
    """One searchable KB branch (a fact block for the bot)."""

    id: str
    title: str
    tags: frozenset[str] = frozenset()
    series: frozenset[str] = frozenset()
    tokens: frozenset[str] = frozenset()
    gotos: frozenset[tuple[str, str]] = frozenset()
    body: str = ""


class _BranchDraft(TypedDict):
    id: str
    tags: frozenset[str]
    series: frozenset[str]
    tokens: frozenset[str]
    gotos: list[tuple[str, str]]
    title: str


@dataclass(frozen=True, slots=True)
class KbFileMeta:
    version: int
    built_at: str
    branch_count: int


def _split_csv(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(part.strip().casefold() for part in raw.split(",") if part.strip())


def _slug_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _branch_search_blob(branch: KbBranch) -> str:
    goto_keys = " ".join(key for key, _ in branch.gotos)
    return " ".join(
        (
            branch.id,
            branch.title,
            " ".join(branch.tags),
            " ".join(branch.series),
            " ".join(branch.tokens),
            goto_keys,
            branch.body,
        ),
    ).casefold()


def format_branch_block(branch: KbBranch) -> str:
    """Serialize one branch with machine-readable markers."""
    tag_csv = ",".join(sorted(branch.tags))
    lines = [f"@BRANCH BEGIN id={branch.id} tags={tag_csv}"]
    if branch.series:
        lines[0] += f" series={','.join(sorted(branch.series))}"
    if branch.tokens:
        lines[0] += f" tokens={','.join(sorted(branch.tokens))}"
    lines.append(f"@TITLE {branch.title}")
    for key, target in sorted(branch.gotos):
        lines.append(f"@GOTO {key} → {target}")
    if branch.body.strip():
        lines.append(branch.body.rstrip())
    lines.append("@BRANCH END")
    return "\n".join(lines)


def format_bot_kb_document(
    branches: list[KbBranch],
    *,
    meta: KbFileMeta,
) -> str:
    """Render the committed single-file bot KB."""
    raw_lines = [
        "# База знаний бота Hoocon — единственный источник ответов",
        "",
        f"@META version={meta.version} built_at={meta.built_at} branches={meta.branch_count}",
        "",
        "Формат: @BRANCH BEGIN … @BRANCH END. Бот отвечает только по веткам ниже.",
        "@GOTO — подсказки умного поиска (токен → id ветки).",
        "",
    ]
    lines: list[str] = []
    _append_wrapped_lines(lines, "\n".join(raw_lines))
    lines.append("")
    for branch in branches:
        block = format_branch_block(branch)
        _append_wrapped_lines(lines, block)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_bot_kb_meta(text: str) -> KbFileMeta | None:
    for line in text.splitlines():
        match = _META_RE.match(line.strip())
        if match:
            return KbFileMeta(
                version=int(match.group(1)),
                built_at=match.group(2),
                branch_count=int(match.group(3)),
            )
    return None


def parse_kb_branches(text: str) -> tuple[KbBranch, ...]:
    """Parse all @BRANCH blocks from the KB file."""
    branches: list[KbBranch] = []
    current: _BranchDraft | None = None
    body_lines: list[str] = []

    def flush() -> None:
        nonlocal current, body_lines
        if not current:
            body_lines = []
            return
        branches.append(
            KbBranch(
                id=str(current["id"]),
                title=str(current.get("title") or current["id"]),
                tags=frozenset(current.get("tags") or ()),
                series=frozenset(current.get("series") or ()),
                tokens=frozenset(current.get("tokens") or ()),
                gotos=frozenset(current.get("gotos") or ()),
                body="\n".join(body_lines).strip(),
            ),
        )
        current = None
        body_lines = []

    for line in text.splitlines():
        begin = _BRANCH_BEGIN_RE.match(line.strip())
        if begin:
            flush()
            attrs = _parse_branch_begin_attrs(begin.group(1))
            current = _BranchDraft(
                id=attrs.get("id", "").strip(),
                tags=_split_csv(attrs.get("tags")),
                series=_split_csv(attrs.get("series")),
                tokens=_split_csv(attrs.get("tokens")),
                gotos=[],
                title="",
            )
            continue
        if _BRANCH_END_RE.match(line.strip()):
            flush()
            continue
        if current is None:
            continue
        title = _TITLE_RE.match(line.strip())
        if title:
            current["title"] = title.group(1).strip()
            continue
        goto = _GOTO_RE.match(line.strip())
        if goto:
            current["gotos"].append(
                (goto.group(1).strip().casefold(), goto.group(2).strip()),
            )
            continue
        body_lines.append(line)

    flush()
    return tuple(branches)


@lru_cache(maxsize=1)
def load_kb_branches(path: Path | None = None) -> tuple[KbBranch, ...]:
    kb_path = (path or PACKAGED_KB_PATH).resolve()
    if not kb_path.is_file():
        return ()
    try:
        text = kb_path.read_text(encoding="utf-8")
    except OSError:
        return ()
    if "@BRANCH BEGIN" in text:
        return parse_kb_branches(text)
    return ()


def _score_branch(branch: KbBranch, query: str, goto_targets: set[str]) -> int:
    q = query.casefold()
    score = 0
    volt = extract_voltage_hint(query)
    if branch.id in goto_targets:
        score += 120
    if "_always" in branch.tags or branch.id == _POLICY_BRANCH_ID:
        score += 1_000
    blob = _branch_search_blob(branch)
    for token in extract_sku_tokens(query):
        if token in branch.tokens or token in branch.series:
            score += 80
        if volt and token.endswith(volt) and token in branch.tokens:
            score += 100
        if token in branch.id.casefold() or token in blob:
            score += 40
    if volt == "24":
        if any(tok.endswith("24") and ("mu" in tok or "fu" in tok) for tok in branch.tokens):
            score += 35
        if re.search(r"(?:mu|fu|mqu)230", blob) and not re.search(r"(?:mu|fu|mqu)24", blob):
            score -= 60
    if volt == "230":
        if any(tok.endswith("230") and ("mu" in tok or "fu" in tok) for tok in branch.tokens):
            score += 35
    for tag in branch.tags:
        if len(tag) >= 3 and tag in q:
            score += 12
    for word in re.findall(r"[a-zа-яё0-9]{4,}", q):
        if word in blob:
            score += 3
    return score


def _resolve_goto_targets(branches: tuple[KbBranch, ...], query: str) -> set[str]:
    q = query.casefold()
    targets: set[str] = set()
    for branch in branches:
        for key, target in branch.gotos:
            if key in q or key in extract_sku_tokens(query):
                targets.add(target)
    return targets


def select_kb_branches(
    branches: tuple[KbBranch, ...],
    *,
    query: str,
    max_chars: int,
) -> list[KbBranch]:
    """Pick branches for the prompt (policy always; rest by relevance)."""
    if not branches:
        return []
    goto_targets = _resolve_goto_targets(branches, query)
    scored = [(branch, _score_branch(branch, query, goto_targets)) for branch in branches]
    max_score = max(score for _, score in scored) if scored else 0
    min_score = 20 if max_score >= 50 else 0
    ranked = sorted(scored, key=lambda row: (-row[1], row[0].id))
    selected: list[KbBranch] = []
    used = 0
    for branch, score in ranked:
        if branch.id == _INDEX_BRANCH_ID and score < 50:
            continue
        if score < min_score and branch.id not in {_POLICY_BRANCH_ID} and "_always" not in branch.tags:
            continue
        block = f"## [{branch.id}] {branch.title}\n{branch.body}"
        if used and used + len(block) + 2 > max_chars:
            if branch.id == _POLICY_BRANCH_ID and branch not in selected:
                pass
            elif score < 30:
                continue
            if used + len(block) + 2 > max_chars:
                if used == 0 and max_chars > 300:
                    trimmed = block[: max_chars - 1] + "…"
                    selected.append(
                        KbBranch(
                            branch.id,
                            branch.title,
                            branch.tags,
                            branch.series,
                            branch.tokens,
                            branch.gotos,
                            trimmed.split("\n", 1)[-1],
                        ),
                    )
                break
        if branch in selected:
            continue
        selected.append(branch)
        used += len(block) + 2
    policy = next((b for b in branches if b.id == _POLICY_BRANCH_ID), None)
    if policy and policy not in selected:
        selected.insert(0, policy)
    return selected


def search_kb_context(
    query: str,
    *,
    max_chars: int = 18_000,
    path: Path | None = None,
) -> str:
    """Build prompt context from the single KB file only."""
    branches = load_kb_branches(path)
    if not branches:
        return "Файл gigachat_kb.txt не найден или пуст. Локально: ./scripts/build-gigachat-kb.sh"
    picked = select_kb_branches(branches, query=query, max_chars=max_chars)
    if not picked:
        return "В gigachat_kb.txt нет подходящих веток для запроса."
    volt = extract_voltage_hint(query)
    volt_line = ""
    if volt == "24":
        volt_line = "Клиент указал 24 В: предлагай только артикулы с суффиксом 24 (например DA2MU24), не 230.\n"
    elif volt == "230":
        volt_line = "Клиент указал 230 В: предлагай только артикулы с суффиксом 230 (например DA2MU230), не 24.\n"
    header = f"Выбрано веток: {len(picked)}. Отвечай только по блокам ниже; если факта нет — [ESCALATE].\n{volt_line}"
    parts = [f"## [{branch.id}] {branch.title}\n{branch.body}" for branch in picked]
    body = "\n\n".join(parts)
    if len(header) + len(body) <= max_chars:
        return header + body
    return body[: max_chars - 1] + "…"


def build_policy_branch() -> KbBranch:
    """Static bot policy — always in the KB file."""
    body = """\
Правила (обязательны):
1. Отвечай ТОЛЬКО по веткам @BRANCH этого файла gigachat_kb.txt.
2. Запрещено додумывать ТТХ, артикулы, цены, наличие, сроки, аналоги.
3. Нет ветки или нет факта в ветке → честно скажи и добавь [ESCALATE].
4. Сфера: ОВК / HVAC (заслонки, клапаны, шаровые краны). Не ворота, двери, шлагбаумы.
5. Серии DA…MU / SA…MU: цифра перед MU — номинальный момент в Н·м (DA2MU = 2 Н·м).
6. Напряжение в артикуле: …24 = AC/DC 24 В; …230 = AC 100…240 В. Не путай SKU.
7. Цены и КП — только менеджер ([ESCALATE]).
8. Ссылки — путями с сайта: /catalog, /consultation, /gde-kupit, /faq, /dokumentaciya."""
    return KbBranch(
        id=_POLICY_BRANCH_ID,
        title="Политика ответов бота",
        tags=frozenset({"_always", "policy", "овк", "эскалация"}),
        body=body,
    )


def build_index_branch(branches: list[KbBranch]) -> KbBranch:
    """Navigation map for smart search (@GOTO targets)."""
    lines: list[str] = [
        "Карта веток (для умного поиска). Если вопрос про модель — ищи ветку manual.*",
        "",
    ]
    gotos: list[tuple[str, str]] = []
    for branch in branches:
        if branch.id in {_POLICY_BRANCH_ID, _INDEX_BRANCH_ID}:
            continue
        tag_preview = ",".join(sorted(tag for tag in branch.tags if not tag.startswith("_"))[:6])
        lines.append(f"- {branch.id} — {branch.title}" + (f" [{tag_preview}]" if tag_preview else ""))
        for token in branch.tokens:
            if len(token) >= 4:
                gotos.append((token, branch.id))
        for series in branch.series:
            gotos.append((series.casefold(), branch.id))
    # Deduplicate gotos, keep most specific ids first
    seen: set[tuple[str, str]] = set()
    unique_gotos: list[tuple[str, str]] = []
    for key, target in sorted(gotos, key=lambda row: (-len(row[0]), row[0])):
        pair = (key, target)
        if pair in seen:
            continue
        seen.add(pair)
        unique_gotos.append(pair)
    return KbBranch(
        id=_INDEX_BRANCH_ID,
        title="Карта веток (навигация)",
        tags=frozenset({"_index", "навигация", "поиск"}),
        gotos=frozenset(unique_gotos[:400]),
        body="\n".join(lines),
    )


_SKU_CODE_RE = re.compile(
    r"(?i)((?:DA|SA|HV)\d+(?:MU|FU|MQU)(?:24|230)(?:[-/][A-Z]{1,3})*)",
)


def _is_clean_sku(sku: str) -> bool:
    """Reject PDF glue like ``DA2MU24-D/DSDA2MU230-D/DS``."""
    if len(sku) > 20:
        return False
    return not re.search(r"(?i)(?:24|230)[-/A-Z]*(?:DA|SA|HV)\d", sku)


def _build_voltage_sku_table(body: str) -> str:
    """Canonical SKU ↔ voltage lines at the top of a manual branch."""
    rows: list[str] = []
    seen: set[str] = set()
    bullet_re = re.compile(
        r"(?i)^[–\-]\s*((?:DA|SA|HV)\d+(?:MU|FU|MQU)(?:24|230)(?:[-/][A-Z]+)*)",
    )
    candidates: list[str] = []
    for line in body.splitlines():
        bullet = bullet_re.match(line.strip())
        if bullet:
            candidates.append(bullet.group(1))
    if not candidates:
        candidates = [match.group(1) for match in _SKU_CODE_RE.finditer(body)]
    for raw in candidates:
        sku = raw.upper()
        if not _is_clean_sku(sku):
            continue
        key = re.sub(r"[^A-Z0-9]", "", sku)
        if key in seen:
            continue
        seen.add(key)
        volt = re.search(r"(?:MU|FU|MQU)(24|230)", sku, re.I)
        if not volt:
            continue
        label = f"AC/DC {volt.group(1)} В" if volt.group(1) == "24" else "AC 100…240 В"
        rows.append(f"- {sku} — {label}")
    if not rows:
        return ""
    return "Артикулы и напряжение (канон):\n" + "\n".join(rows)


def tokens_from_manual_content(label: str, body: str) -> frozenset[str]:
    """Derive search tokens from manual label and body (incl. …24 / …230 SKU)."""
    tokens: set[str] = set()
    for piece in re.findall(r"[a-z0-9]{3,}", label.casefold()):
        tokens.add(piece)
    for sku in extract_sku_tokens(label):
        tokens.add(sku)
    stem = Path(label.split("—")[0].split()[-1]).stem
    if stem:
        tokens.add(_slug_token(stem))
    mu = re.search(r"da(\d+)mu", label, re.I)
    if mu:
        tokens.add(f"da{mu.group(1)}mu")
    for match in _SKU_CODE_RE.finditer(body):
        raw = match.group(1)
        if not _is_clean_sku(raw):
            continue
        slug = _slug_token(raw)
        tokens.add(slug)
        core = re.match(r"(?i)((?:da|sa|hv)\d+(?:mu|fu|mqu))(24|230)", raw)
        if core:
            tokens.add((core.group(1) + core.group(2)).casefold())
    return frozenset(tokens)


def tokens_from_manual_label(label: str) -> frozenset[str]:
    """Derive search tokens from a manual branch label only."""
    return tokens_from_manual_content(label, "")


def series_from_manual_label(label: str) -> frozenset[str]:
    series: set[str] = set()
    for match in re.finditer(r"(?i)(?:da|sa)\d+mu", label):
        series.add(match.group(0).casefold())
    return frozenset(series)
