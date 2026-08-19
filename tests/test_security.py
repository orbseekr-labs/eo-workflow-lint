"""Security and privacy requirements (SPECIFICATION §19)."""

from __future__ import annotations

import ast
import socket
from pathlib import Path

import pytest

import eo_workflow_lint
from support import LC08_ASSET, analyze, codes, run_cli

PACKAGE_ROOT = Path(eo_workflow_lint.__file__).parent
REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_MODULES = sorted(PACKAGE_ROOT.rglob("*.py"))

FORBIDDEN_IMPORTS = {
    "socket",
    "ssl",
    "http",
    "http.client",
    "urllib",
    "urllib.request",
    "urllib.parse",
    "ftplib",
    "smtplib",
    "telnetlib",
    "asyncio",
    "requests",
    "httpx",
    "aiohttp",
    "subprocess",
    "multiprocessing",
    "ee",
    "earthengine_api",
    "openai",
    "anthropic",
}


def test_runtime_package_has_modules_to_audit() -> None:
    assert len(RUNTIME_MODULES) >= 8


@pytest.mark.parametrize("module_path", RUNTIME_MODULES, ids=lambda p: p.name)
def test_no_network_telemetry_or_process_imports(module_path: Path) -> None:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not (imported & FORBIDDEN_IMPORTS), f"{module_path.name}: {imported & FORBIDDEN_IMPORTS}"


@pytest.mark.parametrize("module_path", RUNTIME_MODULES, ids=lambda p: p.name)
def test_no_dynamic_execution_primitives(module_path: Path) -> None:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    # Bare builtins that would execute or dynamically load code.
    forbidden_builtins = {"eval", "exec", "compile", "__import__", "open"}
    # Attribute calls that would execute code or spawn a process. ``re.compile``
    # is regex construction, not code execution, so ``compile`` is not listed here;
    # ``subprocess.run``/``call`` cannot occur because the import itself is banned
    # by test_no_network_telemetry_or_process_imports.
    forbidden_attributes = {"eval", "exec", "system", "popen", "spawn", "spawnv", "fork"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_builtins, f"{module_path.name}: {node.func.id}()"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_attributes, (
                f"{module_path.name}: .{node.func.attr}()"
            )


@pytest.mark.parametrize("module_path", RUNTIME_MODULES, ids=lambda p: p.name)
def test_no_environment_or_credential_access(module_path: Path) -> None:
    source = module_path.read_text(encoding="utf-8")
    for forbidden in ("os.environ", "getenv", "expanduser", "netrc", "getpass"):
        assert forbidden not in source, f"{module_path.name}: {forbidden}"


def test_installed_distribution_declares_no_runtime_dependencies() -> None:
    """The real runtime dependency surface, as recorded in installed metadata."""
    from importlib.metadata import requires

    declared = requires("eo-workflow-lint") or []
    # Only extras (e.g. the `dev` extra) may appear; nothing unconditional.
    unconditional = [item for item in declared if "extra ==" not in item]
    assert unconditional == [], unconditional


def test_pyproject_declares_no_runtime_dependencies() -> None:
    import tomllib

    pyproject = REPO_ROOT / "pyproject.toml"
    if not pyproject.exists():  # running against an installed build outside the repo
        pytest.skip("pyproject.toml is not available in this checkout")
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == []


def test_analysis_works_with_networking_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object):
        raise AssertionError("eo-workflow-lint attempted network access")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)

    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL201"]


def test_cli_works_with_networking_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args: object, **kwargs: object):
        raise AssertionError("eo-workflow-lint attempted network access")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)

    target = tmp_path / "workflow.py"
    target.write_text(
        f'import ee\nimg = ee.Image("{LC08_ASSET}")\n'
        'ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])\n',
        encoding="utf-8",
    )
    code, out, _ = run_cli(["check", str(target), "--format", "json"])
    assert code == 1
    assert '"EWL201"' in out
    assert run_cli(["rules"])[0] == 0
    assert run_cli(["sources"])[0] == 0
    assert run_cli(["explain", "EWL301"])[0] == 0


def test_analyzed_source_is_never_executed() -> None:
    """The fixture writes a marker file at import time; analysis must not run it."""
    fixture = Path(__file__).parent / "fixtures" / "side_effect.py"
    marker = fixture.with_name("SIDE_EFFECT_MARKER")
    if marker.exists():
        marker.unlink()

    import sys

    modules_before = set(sys.modules)
    code, _, _ = run_cli(["check", str(fixture)])

    assert code == 0
    assert not marker.exists()
    assert "side_effect" not in {
        name.rsplit(".", 1)[-1] for name in set(sys.modules) - modules_before
    }


def test_analyzer_does_not_write_to_the_analyzed_directory(tmp_path: Path) -> None:
    target = tmp_path / "workflow.py"
    target.write_text(f'import ee\nimg = ee.Image("{LC08_ASSET}")\n', encoding="utf-8")
    before = sorted(p.name for p in tmp_path.iterdir())
    run_cli(["check", str(target), "--format", "json"])
    assert sorted(p.name for p in tmp_path.iterdir()) == before
