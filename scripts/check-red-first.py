#!/usr/bin/env python3
"""Red-first check: changed tests must fail on the code before the change.

Runs the added / modified test functions of the current diff against ``HEAD``
production code in a throwaway worktree. If every one of them passes there,
the tests do not depend on the change — they confirm the code instead of
catching the bug (.cursor/rules/tests-catch-bugs.mdc).

Exit 0 — at least one changed test is red on HEAD, or the check does not apply.
Exit 1 — all changed tests are green without the change.

Opt out for a pure refactor: ``RED_FIRST_SKIP="причина" ./scripts/pre-commit-checkup.sh``.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
BACKEND = "backend/"
TESTS = "backend/tests/"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout


def changed_paths() -> list[str]:
    """Staged paths, or unstaged + untracked when nothing is staged (same scope as checkup)."""
    staged = git("diff", "--cached", "--name-only", "--diff-filter=ACMR").split()
    if staged:
        return staged
    unstaged = git("diff", "--name-only", "--diff-filter=ACMR").split()
    untracked = git("ls-files", "--others", "--exclude-standard", "--", BACKEND).split()
    return unstaged + untracked


def collect_test_defs(source: str) -> dict[str, str]:
    """``{"test_x" | "TestY::test_x": ast dump}`` for every test in ``source``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test"):
            found[node.name] = ast.dump(node, include_attributes=False)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for item in node.body:
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef) and item.name.startswith("test"):
                    found[f"{node.name}::{item.name}"] = ast.dump(item, include_attributes=False)
    return found


def changed_tests(old_source: str, new_source: str) -> list[str]:
    """Names of tests that are new or whose body changed."""
    old = collect_test_defs(old_source)
    return [name for name, dump in collect_test_defs(new_source).items() if old.get(name) != dump]


def head_source(path: str) -> str:
    return git("show", f"HEAD:{path}")


def tests_are_red(returncode: int, report_lines: list[str]) -> bool:
    """Changed tests do not pass on the code before the change.

    Pytest exits 4 when a new test file cannot be collected, usually because
    it imports a module that does not exist yet. That is still a red result:
    the tests depend on the change and never reach a passing assert.
    """
    if returncode in (1, 2):
        return True
    return returncode == 4 and any(line.startswith("ERROR ") for line in report_lines)


def venv_python() -> str:
    override = os.environ.get("RED_FIRST_PYTHON", "").strip()
    if override:
        return override
    env_path = subprocess.run(
        ["poetry", "env", "info", "-p"], cwd=ROOT / "backend", capture_output=True, text=True, check=False
    ).stdout.strip()
    candidate = Path(env_path) / "bin" / "python" if env_path else ROOT / "backend" / ".venv" / "bin" / "python"
    return str(candidate)


def main() -> int:
    skip_reason = os.environ.get("RED_FIRST_SKIP", "").strip()
    if skip_reason:
        print(f"Red-first пропущен: {skip_reason}")
        return 0

    paths = changed_paths()
    test_files = [p for p in paths if p.startswith(TESTS) and (ROOT / p).is_file()]
    prod_changed = [p for p in paths if p.startswith(BACKEND) and not p.startswith(TESTS)]
    if not prod_changed:
        print("Red-first: код backend не менялся — проверка не нужна")
        return 0
    if not test_files:
        print("Red-first: код изменён без тестов (для Fixed… нужен регресс-тест)")
        return 0

    node_ids = [
        f"{path.removeprefix(BACKEND)}::{name}"
        for path in test_files
        if path.endswith(".py")
        for name in changed_tests(head_source(path), (ROOT / path).read_text(encoding="utf-8"))
    ]
    if not node_ids:
        print("Red-first: тест-функции не менялись — проверка не нужна")
        return 0

    workdir = Path(tempfile.mkdtemp(prefix="hoocon-red-first-"))
    try:
        subprocess.run(["git", "worktree", "add", "-q", "--detach", str(workdir), "HEAD"], cwd=ROOT, check=True)
        for path in test_files:
            target = workdir / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, target)
        if (ROOT / ".env").is_file():
            shutil.copy2(ROOT / ".env", workdir / ".env")
        env = {**os.environ, "CELERY_TASK_ALWAYS_EAGER": "true"}
        result = subprocess.run(
            [venv_python(), "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", *node_ids],
            cwd=workdir / "backend",
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(workdir)], cwd=ROOT, check=False)
        shutil.rmtree(workdir, ignore_errors=True)

    summary = [line for line in result.stdout.splitlines() if line.startswith(("FAILED", "ERROR"))]
    tail = result.stdout.strip().splitlines()[-1:] or [""]
    print(f"Red-first: {len(node_ids)} изменённых тестов на коде из HEAD → {tail[0]}")
    if tests_are_red(result.returncode, summary):
        for line in summary[:10]:
            print(f"  красный без правки: {line}")
        return 0
    if result.returncode == 0:
        print("  Все изменённые тесты зелёные без правки кода — они не ловят то, что меняет коммит.")
        print("  Проверь: тест на симптом, негативный кейс, ожидание из источника (tests-catch-bugs.mdc).")
        print('  Чистый рефакторинг: RED_FIRST_SKIP="причина" ./scripts/pre-commit-checkup.sh')
        for node in node_ids[:10]:
            print(f"    {node}")
        return 1
    print(f"  pytest завершился с кодом {result.returncode} — проверка не выполнена")
    print("\n".join(result.stdout.splitlines()[-15:]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
