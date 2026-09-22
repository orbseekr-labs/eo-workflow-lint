"""GitHub Action runner (``action/run.py``) behaviour.

The runner is an integration layer over the public library API. These tests
call its functions directly with temporary workspaces; one test also drives the
real ``git ls-files -z`` discovery used by ``action.yml``.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from eo_workflow_lint.analyzer import analyze_source
from eo_workflow_lint.serialization import to_json

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "action" / "run.py"
ACTION_YML = REPO_ROOT / "action.yml"


def _load_runner():
    spec = importlib.util.spec_from_file_location("ewl_action_run", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()

CLEAN = (REPO_ROOT / "examples" / "clean_workflow.py").read_text(encoding="utf-8")
CONDITIONAL = (REPO_ROOT / "examples" / "landsat_ndvi_scaled_negative_mask.py").read_text(
    encoding="utf-8"
)
FAIL = (REPO_ROOT / "examples" / "landsat_ndvi_unscaled.py").read_text(encoding="utf-8")
BROKEN = "def broken(:\n"


class Run:
    """Result of one runner invocation against a temporary workspace."""

    def __init__(self, workspace: Path, files: dict[str, str | bytes], fail_on: str) -> None:
        for rel, content in files.items():
            target = workspace / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding="utf-8")
        self.summary_path = workspace / "_summary.md"
        self.outputs_path = workspace / "_outputs.txt"
        out = io.StringIO()
        self.exit_code = runner.run(
            list(files),
            fail_on=fail_on,
            workspace=workspace,
            summary_path=self.summary_path,
            outputs_path=self.outputs_path,
            out=out,
        )
        self.stdout = out.getvalue()
        self.summary = self.summary_path.read_text(encoding="utf-8")
        self.outputs = dict(
            line.split("=", 1)
            for line in self.outputs_path.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )

    @property
    def annotations(self) -> list[str]:
        return [line for line in self.stdout.splitlines() if line.startswith("::")]

    def annotations_of(self, level: str) -> list[str]:
        return [a for a in self.annotations if a.startswith(f"::{level} ")]


# ------------------------------------------------------------------ outcomes


def test_no_python_files(tmp_path: Path) -> None:
    run = Run(tmp_path, {}, "fail")
    assert run.exit_code == 0
    assert run.annotations == []
    assert run.outputs["files-checked"] == "0"
    assert run.outputs["verdict"] == "PASS"
    assert "| Python files checked | 0 |" in run.summary


def test_non_python_paths_are_ignored(tmp_path: Path) -> None:
    run = Run(tmp_path, {"README.md": "# hi", "data.json": "{}"}, "fail")
    assert run.exit_code == 0
    assert run.outputs["files-checked"] == "0"


def test_clean_workflow_passes(tmp_path: Path) -> None:
    run = Run(tmp_path, {"workflow.py": CLEAN}, "conditional")
    assert run.exit_code == 0
    assert run.annotations == []
    assert run.outputs["verdict"] == "PASS"
    assert run.outputs["files-checked"] == "1"
    assert run.outputs["findings"] == "0"


def test_one_conditional_finding_with_fail_on_fail(tmp_path: Path) -> None:
    run = Run(tmp_path, {"ndvi.py": CONDITIONAL}, "fail")
    assert run.exit_code == 0
    assert len(run.annotations_of("warning")) == 1
    assert run.annotations_of("error") == []
    assert run.outputs["verdict"] == "CONDITIONAL"
    assert run.outputs["conditional-count"] == "1"


def test_one_conditional_finding_with_fail_on_conditional(tmp_path: Path) -> None:
    run = Run(tmp_path, {"ndvi.py": CONDITIONAL}, "conditional")
    assert run.exit_code == 1
    assert len(run.annotations_of("warning")) == 1
    assert run.outputs["verdict"] == "CONDITIONAL"


@pytest.mark.parametrize("fail_on", ["fail", "conditional"])
def test_one_fail_finding_fails_regardless_of_threshold(tmp_path: Path, fail_on: str) -> None:
    run = Run(tmp_path, {"raw.py": FAIL}, fail_on)
    assert run.exit_code == 1
    assert len(run.annotations_of("error")) == 1
    assert run.outputs["verdict"] == "FAIL"
    assert run.outputs["fail-count"] == "1"


def test_mixed_findings_across_multiple_files(tmp_path: Path) -> None:
    files = {"a/raw.py": FAIL, "b/ndvi.py": CONDITIONAL, "c/clean.py": CLEAN}
    run = Run(tmp_path, files, "fail")
    assert run.exit_code == 1
    assert run.outputs["files-checked"] == "3"
    assert run.outputs["findings"] == "2"
    assert run.outputs["fail-count"] == "1"
    assert run.outputs["conditional-count"] == "1"
    assert run.outputs["verdict"] == "FAIL"
    assert "| PASS / CONDITIONAL / FAIL | 1 / 1 / 1 |" in run.summary
    assert "| Findings | 2 (1 FAIL, 1 CONDITIONAL) |" in run.summary
    assert "| `a/raw.py` | 6 | EWL201 | FAIL |" in run.summary
    assert "| `b/ndvi.py` | 14 | EWL203 | CONDITIONAL |" in run.summary


def test_invalid_fail_on_value(tmp_path: Path) -> None:
    out = io.StringIO()
    code = runner.run(
        [], fail_on="maybe", workspace=tmp_path, summary_path=None, outputs_path=None, out=out
    )
    assert code == 2
    assert "::error" in out.getvalue()


# --------------------------------------------------------------- annotations


def test_annotation_contains_file_line_code_and_message(tmp_path: Path) -> None:
    run = Run(tmp_path, {"src/raw.py": FAIL}, "fail")
    (annotation,) = run.annotations_of("error")
    props, _, message = annotation[len("::error ") :].partition("::")
    assert "file=src/raw.py" in props
    assert "line=6" in props
    assert "col=8" in props
    assert "title=EWL201 LANDSAT_C2_SR_UNSCALED_NORMALIZED_DIFFERENCE" in props
    assert message.startswith("Landsat Collection 2 Level-2 surface-reflectance bands")


def test_conditional_finding_is_a_warning_annotation(tmp_path: Path) -> None:
    run = Run(tmp_path, {"ndvi.py": CONDITIONAL}, "fail")
    (annotation,) = run.annotations_of("warning")
    assert "file=ndvi.py" in annotation
    assert "line=14" in annotation
    assert "title=EWL203 NORMALIZED_DIFFERENCE_NEGATIVE_MASK_RISK" in annotation


def test_annotation_escaping_follows_workflow_command_rules() -> None:
    assert runner._escape_data("a%b\r\nc") == "a%25b%0D%0Ac"
    assert runner._escape_property("x:y,z%") == "x%3Ay%2Cz%25"
    text = runner._annotation("error", "m", file="dir:a,b.py", title="t")
    assert text == "::error file=dir%3Aa%2Cb.py,title=t::m"


def test_filenames_with_spaces_and_unicode(tmp_path: Path) -> None:
    files = {"sub dir/my workflow.py": FAIL, "植生 ndvi.py": CONDITIONAL}
    run = Run(tmp_path, files, "fail")
    assert run.exit_code == 1
    assert any("file=sub dir/my workflow.py" in a for a in run.annotations_of("error"))
    assert any("file=植生 ndvi.py" in a for a in run.annotations_of("warning"))
    assert "`sub dir/my workflow.py`" in run.summary
    assert "`植生 ndvi.py`" in run.summary


# ----------------------------------------------------- unanalyzable / errors


def test_syntax_error_is_distinct_and_exits_two(tmp_path: Path) -> None:
    run = Run(tmp_path, {"broken.py": BROKEN, "clean.py": CLEAN}, "fail")
    assert run.exit_code == 2
    (annotation,) = run.annotations_of("error")
    assert "file=broken.py" in annotation
    assert "not analyzable" in annotation
    assert "Python syntax error" in annotation
    # Counted separately from scientific findings.
    assert run.outputs["not-analyzable"] == "1"
    assert run.outputs["findings"] == "0"
    assert run.outputs["files-checked"] == "1"
    assert "| Not analyzable | 1 |" in run.summary
    assert "| `broken.py` | Python syntax error" in run.summary


def test_invalid_utf8_is_not_analyzable(tmp_path: Path) -> None:
    run = Run(tmp_path, {"latin.py": b"x = '\xff'\n"}, "fail")
    assert run.exit_code == 2
    assert run.outputs["not-analyzable"] == "1"


def test_invalid_input_takes_precedence_over_threshold(tmp_path: Path) -> None:
    run = Run(tmp_path, {"broken.py": BROKEN, "raw.py": FAIL}, "conditional")
    assert run.exit_code == 2
    # The scientific finding is still reported; only the exit code is overridden.
    assert run.outputs["fail-count"] == "1"
    assert run.outputs["verdict"] == "FAIL"


def test_internal_failure_takes_precedence_and_exits_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_data: bytes):
        raise RuntimeError("synthetic analyzer failure")

    monkeypatch.setattr(runner, "analyze_source", boom)
    run = Run(tmp_path, {"clean.py": CLEAN}, "fail")
    assert run.exit_code == 3
    (annotation,) = run.annotations_of("error")
    assert "internal error" in annotation and "synthetic analyzer failure" in annotation
    assert "| Internal failures | 1 |" in run.summary
    assert run.outputs["exit-code"] == "3"


def test_missing_file_is_not_analyzable(tmp_path: Path) -> None:
    out = io.StringIO()
    code = runner.run(
        ["gone.py"],
        fail_on="fail",
        workspace=tmp_path,
        summary_path=None,
        outputs_path=None,
        out=out,
    )
    assert code == 2
    assert "no such file" in out.getvalue()


# ---------------------------------------------------------- privacy / schema


def test_summary_and_outputs_contain_no_source_code(tmp_path: Path) -> None:
    files = {"a/raw.py": FAIL, "b/ndvi.py": CONDITIONAL, "broken.py": BROKEN}
    run = Run(tmp_path, files, "conditional")
    for content in files.values():
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(("import ", '"""')):
                assert stripped not in run.summary, stripped
                assert stripped not in run.outputs_path.read_text(encoding="utf-8")
    assert "no source code was transmitted" in run.summary


def test_summary_reports_version_and_documentation_link(tmp_path: Path) -> None:
    from eo_workflow_lint import __version__, catalog

    run = Run(tmp_path, {"clean.py": CLEAN}, "fail")
    assert f"eo-workflow-lint {__version__}, catalog {catalog.CATALOG_VERSION}" in run.summary
    assert "https://github.com/orbseekr-labs/eo-workflow-lint" in run.summary
    assert "explain <CODE>" in run.summary


def test_runner_does_not_alter_the_json_report(tmp_path: Path) -> None:
    """The action only reads reports; the deterministic JSON is byte-identical."""
    source = FAIL.encode("utf-8")
    before = to_json(analyze_source(source))
    Run(tmp_path, {"raw.py": FAIL}, "fail")
    after = to_json(analyze_source(source))
    assert before == after
    finding = json.loads(after)["findings"][0]
    assert list(finding) == [
        "code",
        "severity",
        "name",
        "line",
        "column",
        "message",
        "source_ids",
        "evidence",
    ]


def test_runner_imports_no_network_or_process_modules() -> None:
    tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {
        "socket",
        "ssl",
        "http",
        "http.client",
        "urllib",
        "urllib.request",
        "requests",
        "httpx",
        "subprocess",
        "multiprocessing",
        "ee",
    }
    assert not (imported & forbidden), imported & forbidden
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"eval", "exec", "compile", "__import__"}


def test_runner_is_not_shipped_in_the_package() -> None:
    import eo_workflow_lint

    package_root = Path(eo_workflow_lint.__file__).parent
    assert not (package_root / "run.py").exists()
    assert "action" not in {p.name for p in package_root.iterdir()}


# ------------------------------------------------------------- action.yml


def test_action_yml_public_surface() -> None:
    yaml = pytest.importorskip("yaml")
    action = yaml.safe_load(ACTION_YML.read_text(encoding="utf-8"))
    assert list(action["inputs"]) == ["fail-on", "paths"]
    assert action["inputs"]["fail-on"]["default"] == "fail"
    assert action["inputs"]["paths"]["default"] == "*.py"
    assert action["runs"]["using"] == "composite"
    step = action["runs"]["steps"][-1]
    script = step["run"]
    assert step["shell"] == "bash"
    # Inputs reach the script only through the environment.
    assert "${{ inputs" not in script
    assert 'ls-files -z -- "${PATHSPECS[@]}"' in script
    assert "pip install" not in script
    assert 'PYTHONPATH="$EWL_ACTION_PATH/src"' in script
    for name in ("verdict", "files-checked", "findings", "fail-count", "conditional-count"):
        assert name in action["outputs"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not available")
def test_git_discovery_pipeline_end_to_end(tmp_path: Path) -> None:
    """Drive the exact discovery command from action.yml into the runner."""
    yaml = pytest.importorskip("yaml")
    script = yaml.safe_load(ACTION_YML.read_text(encoding="utf-8"))["runs"]["steps"][-1]["run"]

    repo = tmp_path / "repo"
    files = {
        "sub dir/clean workflow.py": CLEAN,
        "植生 ndvi.py": CONDITIONAL,
        "notebooks/raw.py": FAIL,
        "README.md": "not python\n",
    }
    for rel, content in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(content, encoding="utf-8")
    git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], cwd=repo, check=True)
    subprocess.run([*git, "add", "-A"], cwd=repo, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "init"], cwd=repo, check=True)

    # ``python`` resolves to the test interpreter, as actions/setup-python provides it.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python").symlink_to(sys.executable)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "GITHUB_WORKSPACE": str(repo),
        "EWL_ACTION_PATH": str(REPO_ROOT),
        "INPUT_FAIL_ON": "conditional",
        "INPUT_PATHS": "*.py\n:!notebooks/**\n",
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "GITHUB_OUTPUT": str(tmp_path / "outputs.txt"),
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
    }
    proc = subprocess.run(["bash", "-c", script], cwd=repo, env=env, capture_output=True, text=True)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "file=植生 ndvi.py" in proc.stdout
    assert "notebooks/raw.py" not in proc.stdout
    outputs = (tmp_path / "outputs.txt").read_text(encoding="utf-8")
    assert "files-checked=2" in outputs
    assert "verdict=CONDITIONAL" in outputs
