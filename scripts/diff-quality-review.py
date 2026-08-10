#!/usr/bin/env python3
"""Static diff review: bugs, knowledge-base standards, security (Hoocon CMS).

Scans staged or unstaged git changes. Exit 0 = clean, 1 = blocking findings.
Used by ``scripts/pre-commit-checkup.sh``.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(
    subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
    ).strip(),
)

# Blocking patterns on *added* lines (path → list of (regex, code, message)).
_SECURITY_ADDED: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\beval\s*\("), "SEC001", "eval() запрещён (инъекции)"),
    (re.compile(r"\bexec\s*\("), "SEC002", "exec() запрещён"),
    (re.compile(r"\bpickle\.loads\s*\("), "SEC003", "pickle.loads небезопасен"),
    (re.compile(r"\byaml\.load\s*\("), "SEC004", "yaml.load без SafeLoader запрещён"),
    (re.compile(r"shell\s*=\s*True"), "SEC005", "subprocess shell=True запрещён"),
    (
        re.compile(r"""HttpResponseRedirect\s*\(\s*request\.(GET|POST)"""),
        "SEC006",
        "open redirect: не редиректить на request.GET/POST без allowlist",
    ),
    (
        re.compile(r"""redirect\s*\(\s*request\.(GET|POST)"""),
        "SEC007",
        "open redirect: redirect(request.GET/POST) без allowlist",
    ),
    (
        re.compile(r"""\.raw\s*\(\s*f["']|\.execute\s*\(\s*f["']"""),
        "SEC008",
        "f-string SQL (.raw/.execute) — только ORM или params",
    ),
    (
        re.compile(r"""cursor\.execute\s*\(\s*f["']"""),
        "SEC009",
        "f-string в cursor.execute — SQL injection",
    ),
]

_KB_ADDED: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"from typing import.*\b(List|Dict|Set|Tuple|Optional)\b"),
        "KB001",
        "PEP 585/604: list/dict/set/tuple/X|None вместо typing.List/Optional",
    ),
    (
        re.compile(r"\bOptional\["),
        "KB002",
        "Используй X | None вместо Optional[X] (PEP 604)",
    ),
    (
        re.compile(r"\bList\["),
        "KB003",
        "Используй list[…] вместо List[…] (PEP 585)",
    ),
    (
        re.compile(r"\bDict\["),
        "KB004",
        "Используй dict[…] вместо Dict[…] (PEP 585)",
    ),
    (
        re.compile(r"^\s*except\s*:"),
        "KB005",
        "Голый except: запрещён — except SpecificError",
    ),
    (
        re.compile(r"^\s*except\s+Exception\s*:\s*$"),
        "KB006",
        "except Exception: без имени — логируй type(e).__name__ и сузь тип",
    ),
]

_BUG_ADDED: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"(?:^\s*#\s*|^|\s)(TODO|FIXME|XXX)\b"),
        "BUG001",
        "TODO/FIXME в коммите — закрой или вынеси в issue/план",
    ),
    (
        re.compile(r"assert\s+False\b"),
        "BUG002",
        "assert False в прод-коде — raise ExplicitError",
    ),
]

# Russian ё: high-confidence е-forms that must use ё in site/copy text.
# Do not list ambiguous «все» (all) here.
_YO_ADDED: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bеще\b", re.I), "YO001", "Пиши «ещё», не «еще»"),
    (re.compile(r"\bобъем"), "YO002", "Пиши «объём…», не «объем…»"),
    (re.compile(r"\bпартнер"), "YO003", "Пиши «партнёр…», не «партнер…»"),
    (re.compile(r"\bнадежн", re.I), "YO004", "Пиши «надёжн…», не «надежн…»"),
    (re.compile(r"\bрасчет"), "YO005", "Пиши «расчёт…», не «расчет…»"),
    (re.compile(r"\bсчетчик"), "YO006", "Пиши «счётчик…», не «счетчик…»"),
    (re.compile(r"\bтрех"), "YO007", "Пиши «трёх…», не «трех…»"),
    (re.compile(r"\bчетырех"), "YO008", "Пиши «четырёх…», не «четырех…»"),
    (re.compile(r"\bприем\b"), "YO009", "Пиши «приём», не «прием»"),
    (re.compile(r"\bучет\b"), "YO010", "Пиши «учёт», не «учет»"),
    (re.compile(r"\bучета\b"), "YO011", "Пиши «учёта», не «учета»"),
    (re.compile(r"\bучетн"), "YO012", "Пиши «учётн…», не «учетн…»"),
    (re.compile(r"\bсчет\b"), "YO013", "Пиши «счёт», не «счет»"),
    (re.compile(r"\bсчета\b"), "YO014", "Пиши «счёта», не «счета»"),
    (re.compile(r"\bсчете\b"), "YO015", "Пиши «счёте», не «счете»"),
    (re.compile(r"\bсчету\b"), "YO016", "Пиши «счёту», не «счету»"),
    (re.compile(r"\bсчетом\b"), "YO017", "Пиши «счётом», не «счетом»"),
    (re.compile(r"\bчертеж\b"), "YO018", "Пиши «чертёж» (ед.ч.), не «чертеж»"),
    (re.compile(r"\bлегк"), "YO019", "Пиши «лёгк…», не «легк…»"),
    (re.compile(r"\bжестк"), "YO020", "Пиши «жёстк…», не «жестк…»"),
    (re.compile(r"\bчетк"), "YO021", "Пиши «чётк…», не «четк…»"),
    (re.compile(r"\bидет\b"), "YO022", "Пиши «идёт», не «идет»"),
    (re.compile(r"\bдает\b"), "YO023", "Пиши «даёт», не «дает»"),
    (re.compile(r"\bведется\b"), "YO024", "Пиши «ведётся», не «ведется»"),
]

# Whole-file heuristics on changed admin modules.
_SKIP_PATH_PARTS = (
    "/migrations/",
    "/.venv/",
    "/node_modules/",
    "__pycache__",
)

_ALLOW_TODO_IN = ("/docs/", "/ПЛАН", ".md")


@dataclass
class Finding:
    """One review finding."""

    code: str
    path: str
    line: int
    message: str
    text: str = ""


@dataclass
class Report:
    """Aggregated findings by category."""

    security: list[Finding] = field(default_factory=list)
    kb: list[Finding] = field(default_factory=list)
    bugs: list[Finding] = field(default_factory=list)
    yo: list[Finding] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Count of all findings."""
        return len(self.security) + len(self.kb) + len(self.bugs) + len(self.yo)


def _changed_paths() -> list[str]:
    """Paths from staged diff, or unstaged if nothing staged."""
    staged = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        text=True,
        cwd=ROOT,
    ).strip()
    if staged:
        return [p for p in staged.splitlines() if p]
    unstaged = subprocess.check_output(
        ["git", "diff", "--name-only", "--diff-filter=ACMR"],
        text=True,
        cwd=ROOT,
    ).strip()
    return [p for p in unstaged.splitlines() if p]


def _unified_added_lines(path: str) -> list[tuple[int, str]]:
    """Return (new_lineno, text) for added lines in path."""
    staged = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"],
        text=True,
        cwd=ROOT,
    ).strip()
    args = ["git", "diff", "--unified=0"]
    if staged and path in staged.splitlines():
        args.append("--cached")
    args.extend(["--", path])
    diff = subprocess.check_output(args, text=True, cwd=ROOT, stderr=subprocess.DEVNULL)
    out: list[tuple[int, str]] = []
    new_line = 0
    for raw in diff.splitlines():
        if raw.startswith("@@"):
            # @@ -a,b +c,d @@
            m = re.search(r"\+(\d+)", raw)
            if m:
                new_line = int(m.group(1))
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            out.append((new_line, raw[1:]))
            new_line += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            continue
        elif not raw.startswith("\\"):
            # context line advances new_line in unified=0? with unified=0
            # context is rare; ignore
            pass
    return out


def _should_skip(path: str) -> bool:
    """Skip generated / vendor paths."""
    norm = path.replace("\\", "/")
    return any(part in f"/{norm}/" or part in norm for part in _SKIP_PATH_PARTS)


_YO_TEXT_SUFFIXES = (".py", ".tsx", ".ts", ".html", ".md", ".css")


def _scan_added(path: str, report: Report) -> None:
    """Apply line-level rules to added lines."""
    if _should_skip(path):
        return
    try:
        added = _unified_added_lines(path)
    except subprocess.CalledProcessError:
        return

    allow_todo = any(token in path for token in _ALLOW_TODO_IN)
    is_py = path.endswith(".py")
    is_yo_text = path.endswith(_YO_TEXT_SUFFIXES)
    for lineno, text in added:
        stripped = text.strip()
        if stripped.startswith("#") and "TODO" not in stripped.upper():
            # comments: still scan TODO via BUG001
            pass
        if is_py:
            for pattern, code, msg in _SECURITY_ADDED:
                if pattern.search(text):
                    report.security.append(
                        Finding(code, path, lineno, msg, text.strip())
                    )
            for pattern, code, msg in _KB_ADDED:
                if pattern.search(text):
                    report.kb.append(Finding(code, path, lineno, msg, text.strip()))
            for pattern, code, msg in _BUG_ADDED:
                if code == "BUG001" and allow_todo:
                    continue
                if pattern.search(text):
                    report.bugs.append(Finding(code, path, lineno, msg, text.strip()))
        if is_yo_text:
            # Skip the rule table itself (patterns contain forbidden е-forms).
            if path.replace("\\", "/").endswith("scripts/diff-quality-review.py"):
                continue
            if "re.compile(" in text and ("YO0" in text or "Пиши" in text):
                continue
            for pattern, code, msg in _YO_ADDED:
                if pattern.search(text):
                    report.yo.append(Finding(code, path, lineno, msg, text.strip()))


def _scan_admin_views(path: str, report: Report) -> None:
    """Flag custom admin_view handlers that lack an obvious AuthZ check."""
    if not path.endswith(".py") or "/admin" not in path.replace("\\", "/"):
        # also crm/admin.py leads/admin.py
        if not path.endswith("admin.py"):
            return
    if _should_skip(path):
        return
    full = ROOT / path
    if not full.is_file():
        return
    source = full.read_text(encoding="utf-8")
    for match in re.finditer(
        r"admin_site\.admin_view\s*\(\s*self\.(\w+)\s*\)",
        source,
    ):
        method = match.group(1)
        # Find method body (rough): def method … next def at same indent
        meth_re = re.compile(
            rf"def {re.escape(method)}\s*\(.*?\).*?:\n(.*?)(?=\n    def |\nclass |\Z)",
            re.DOTALL,
        )
        body_m = meth_re.search(source)
        if not body_m:
            continue
        body = body_m.group(1)
        authz_ok = any(
            token in body
            for token in (
                "PermissionDenied",
                "has_perm(",
                "has_change_permission",
                "has_view_permission",
                "has_add_permission",
                "has_delete_permission",
                "user_passes_test",
                "permission_required",
            )
        )
        if not authz_ok:
            line = source[: match.start()].count("\n") + 1
            report.security.append(
                Finding(
                    "SEC010",
                    path,
                    line,
                    (
                        f"admin_view({method}): нет явной проверки прав "
                        "(PermissionDenied / has_*_permission / has_perm)"
                    ),
                    match.group(0),
                ),
            )


def _print_section(title: str, items: list[Finding]) -> None:
    """Print a category section."""
    print(f"\n── {title} ({len(items)}) ──")
    if not items:
        print("  (чисто)")
        return
    for item in items:
        loc = f"{item.path}:{item.line}" if item.line else item.path
        print(f"  [{item.code}] {loc}")
        print(f"      {item.message}")
        if item.text:
            snippet = item.text[:117] + ("…" if len(item.text) > 117 else "")
            print(f"      > {snippet}")


def main() -> int:
    """Run review and print a human-readable report."""
    paths = _changed_paths()
    report = Report()
    if not paths:
        print("Ревью баги/БЗ/security: нет изменённых файлов в diff")
        return 0

    for path in paths:
        _scan_added(path, report)
        _scan_admin_views(path, report)

    print("Ревью diff: баги · стандарты БЗ · безопасность · буква ё")
    print(f"Файлов в diff: {len(paths)}")
    _print_section("Безопасность", report.security)
    _print_section("Стандарты БЗ (стиль/типы/ошибки)", report.kb)
    _print_section("Баги / долги в diff", report.bugs)
    _print_section("Русский текст (буква ё)", report.yo)

    print("")
    if report.total == 0:
        print("✓ Статическое ревью diff — чисто")
        return 0
    print(f"✗ Статическое ревью: {report.total} замечаний (блокирует checkup)")
    print(
        "  Агент: дополнительно проверь IDOR/AuthZ, N+1, mass assignment "
        "по .cursor/rules/pre-commit-checkup.mdc §2–4.",
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
