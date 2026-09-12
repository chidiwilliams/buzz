"""Execute release gates against disposable Git repositories, never origin online."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "Build-BuzzMeeting-Installer-V4.cmd"


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, stderr=subprocess.STDOUT
    ).strip()


@pytest.fixture
def release_repo(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    seed = tmp_path / "seed"
    subprocess.run(
        ["git", "init", "-b", "main", str(seed)], check=True, capture_output=True
    )
    git(seed, "config", "user.email", "test@example.invalid")
    git(seed, "config", "user.name", "Release gate fixture")
    shutil.copy2(ROOT / SCRIPT, seed / SCRIPT)
    (seed / "tracked.txt").write_text("baseline", encoding="utf-8")
    git(seed, "add", ".")
    git(seed, "commit", "-m", "synthetic release fixture")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "origin", "main")
    checkout = tmp_path / "portable release checkout"
    # A separate clone gives this checkout its own local main; .git is a file
    # in the linked worktree tested below.
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-b", "main", str(remote), str(clone)],
        check=True,
        capture_output=True,
    )
    git(clone, "branch", "-m", "holding")
    git(clone, "worktree", "add", "-b", "main", str(checkout), "origin/main")
    assert (checkout / ".git").is_file()
    return seed, checkout, git(seed, "rev-parse", "HEAD")


def invoke(checkout, sha=None, *, tools=None):
    env = os.environ.copy()
    # Keep actual Git/CMD/PowerShell. Deliberately omit build tools so even the
    # successful validation branch cannot build/install from this test fixture.
    system = Path(os.environ["SystemRoot"]) / "System32"
    path = [
        *([str(tools)] if tools is not None else []),
        *[
            str(Path(shutil.which("git")).parent),
            str(system),
            str(system / "WindowsPowerShell" / "v1.0"),
        ],
    ]
    env["PATH"] = os.pathsep.join(path)
    if sha is None:
        env.pop("BUZZ_VALIDATED_SHA", None)
    else:
        env["BUZZ_VALIDATED_SHA"] = sha
    command = f'""{checkout / SCRIPT}""'
    return subprocess.run(
        f'"{system / "cmd.exe"}" /d /s /c {command}',
        cwd=checkout.parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.skipif(os.name != "nt", reason="Executes the Windows CMD entrypoint")
@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "malformed",
        "extra",
        "remote-mismatch",
        "branch",
        "tracked",
        "staged",
        "staged-gitlink",
        "diverged",
        "validated",
        "fast-forward",
        "head-changed-during-update",
        "fetch-failed",
    ],
)
def test_validated_sha_gate(release_repo, case):
    seed, checkout, sha = release_repo
    requested_sha = sha
    expected = "uv is not available"
    if case == "missing":
        requested_sha, expected = None, "Set BUZZ_VALIDATED_SHA"
    elif case == "malformed":
        requested_sha, expected = "main", "Set BUZZ_VALIDATED_SHA"
    elif case == "extra":
        requested_sha, expected = f"{sha} extra", "Set BUZZ_VALIDATED_SHA"
    elif case == "remote-mismatch":
        requested_sha, expected = "0" * 40, "origin/main is no longer"
    elif case == "branch":
        git(checkout, "switch", "-c", "wrong-branch")
        expected = "not on branch main"
    elif case in {"tracked", "staged"}:
        (checkout / "tracked.txt").write_text("dirty", encoding="utf-8")
        if case == "staged":
            git(checkout, "add", "tracked.txt")
        expected = "Staged root" if case == "staged" else "local modifications"
    elif case == "diverged":
        git(checkout, "config", "user.email", "test@example.invalid")
        git(checkout, "config", "user.name", "Release gate fixture")
        git(checkout, "commit", "--allow-empty", "-m", "local-only")
        expected = "not a simple ancestor"
    elif case == "staged-gitlink":
        subprocess.run(
            ["git", "clone", "--shared", str(seed), str(checkout / "dependency")],
            check=True,
            capture_output=True,
        )
        git(
            checkout, "update-index", "--add", "--cacheinfo", f"160000,{sha},dependency"
        )
        expected = "Staged root"
    elif case in {"fast-forward", "head-changed-during-update"}:
        git(seed, "commit", "--allow-empty", "-m", "validated successor")
        git(seed, "push", "origin", "main")
        sha = git(seed, "rev-parse", "HEAD")
        requested_sha = sha
        if case == "head-changed-during-update":
            hooks = checkout.parent / "hooks"
            hooks.mkdir()
            (hooks / "post-merge").write_text(
                "#!/bin/sh\n"
                "git -c user.name=fixture -c user.email=test@example.invalid "
                "commit --allow-empty --no-verify -m unvalidated\n",
                encoding="utf-8",
            )
            git(checkout, "config", "core.hooksPath", str(hooks))
            expected = "Local HEAD did not reach validated target"
    elif case == "fetch-failed":
        git(checkout, "remote", "set-url", "origin", str(checkout / "absent.git"))
        expected = "update/build process failed"
    before = git(checkout, "rev-parse", "HEAD")
    dirt = git(checkout, "status", "--porcelain")
    result = invoke(checkout, requested_sha)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert expected in output, output
    assert "[7/8]" not in output, "Build reached without validation/tool prerequisites"
    head = git(checkout, "rev-parse", "HEAD")
    if case == "head-changed-during-update":
        assert head not in {before, sha}  # The synthetic hook really ran.
    else:
        assert head == (sha if case == "fast-forward" else before)
    assert git(checkout, "status", "--porcelain") == dirt


@pytest.mark.skipif(os.name != "nt", reason="Executes the Windows CMD entrypoint")
@pytest.mark.parametrize(
    "value",
    [
        "",
        "a" * 39,
        "a" * 41,
        "g" + "a" * 39,
        " " + "a" * 40,
        "a" * 40 + " ",
        '"' + "a" * 40 + '"',
    ],
)
def test_rejects_noncanonical_environment_sha_before_fetch(release_repo, value):
    _, checkout, _ = release_repo
    result = invoke(checkout, value)
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Set BUZZ_VALIDATED_SHA" in output
    assert "[1/8]" not in output


INJECTION_VALUES = (
    'abc" & echo INJECTION_SENTINEL & rem "',
    "abc&echo INJECTION_SENTINEL",
    "abc|echo INJECTION_SENTINEL",
    "abc>injection-sentinel.txt",
    "abc%PATH%",
    "abc!PATH!",
)


@pytest.mark.skipif(os.name != "nt", reason="Executes the Windows CMD entrypoint")
@pytest.mark.parametrize("value", INJECTION_VALUES)
def test_sha_environment_is_opaque_before_validation(release_repo, value):
    _, checkout, _ = release_repo
    sentinel = checkout.parent / "injection-sentinel.txt"
    result = invoke(checkout, value)
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "INJECTION_SENTINEL" not in output
    assert not sentinel.exists()
    assert "[1/8]" not in output
    assert "git merge" not in output
    assert "[3/8]" not in output
    assert "[7/8]" not in output


@pytest.mark.skipif(os.name != "nt", reason="Executes the Windows CMD entrypoint")
def test_injection_oracle_kills_unsafe_prevalidation_expansion(release_repo):
    _, checkout, _ = release_repo
    script = checkout / SCRIPT
    text = script.read_text(encoding="utf-8")
    boundary = "powershell.exe -NoProfile -NonInteractive -Command"
    text = text.replace(
        boundary, 'set "UNSAFE_SHA=%BUZZ_VALIDATED_SHA%"\n' + boundary, 1
    )
    script.write_text(text, encoding="utf-8")
    result = invoke(checkout, INJECTION_VALUES[0])
    assert "INJECTION_SENTINEL" in result.stdout + result.stderr


def _write_tool_stubs(root):
    root.mkdir()
    harmless = Path(os.environ["SystemRoot"]) / "System32" / "where.exe"
    for name in ("uv", "make", "cmake", "iscc", "sync"):
        shutil.copy2(harmless, root / f"{name}.exe")
    for name in ("uv", "make", "cmake"):
        (root / name).write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (root / "uv").write_text(
        "#!/usr/bin/env bash\n"
        'test "$*" = "run make bundle_windows" || exit 91\n'
        "pwd -W > observed-build-cwd.txt\n",
        encoding="utf-8",
    )


@pytest.mark.skipif(os.name != "nt", reason="Executes the Windows CMD entrypoint")
def test_valid_sha_build_runs_in_resolved_worktree(release_repo):
    _, checkout, sha = release_repo
    tools = checkout.parent / "controlled build tools"
    _write_tool_stubs(tools)
    dist = checkout / "dist"
    dist.mkdir()
    shutil.copy2(
        Path(os.environ["SystemRoot"]) / "System32" / "where.exe",
        dist / "Buzz-1.4.5-windows.exe",
    )
    result = invoke(checkout, sha, tools=tools)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "[7/8]" in output
    observed = Path((checkout / "observed-build-cwd.txt").read_text().strip())
    assert observed.resolve() == checkout.resolve()
    assert observed.resolve() != checkout.parent.resolve()


def test_release_script_keeps_canonical_pipeline_and_targeted_ctc_safety():
    text = (ROOT / SCRIPT).read_text(encoding="utf-8")
    assert "C:\\Projects\\buzz-meeting" not in text
    assert "/c/Projects/buzz-meeting" not in text
    assert 'set "REPO=%~dp0."' in text
    assert "%~1" not in text and "%1" not in text and "%*" not in text
    validation = text.index("GetEnvironmentVariable('BUZZ_VALIDATED_SHA', 'Process')")
    expansion = text.index('set "EXPECTED_SHA=%BUZZ_VALIDATED_SHA%"')
    assert validation < expansion
    assert '"%GIT_BASH%" -c "uv run make bundle_windows"' in text
    assert text.index('cd /d "%REPO%"') < text.index('"%GIT_BASH%" -c')
    assert text.index("Local HEAD did not reach validated target") < text.index(
        "uv sync"
    )
    assert "git merge --ff-only origin/main" in text
    assert "git -C ctc_forced_aligner ls-files .ruff_cache" in text
    assert 'rmdir /s /q "%CTC_RUFF_CACHE%"' in text
    assert 'set "CTC_RUFF_CACHE=ctc_forced_aligner\\.ruff_cache"' in text
    commands = [line.strip().lower() for line in text.splitlines()]
    assert not any(
        line.startswith(("git reset", "git clean", "git stash")) for line in commands
    )
    assert sum(line.startswith("rmdir ") for line in commands) == 1


def test_ci_dispatch_and_meeting_tag_publish_boundary():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    triggers = workflow.get("on", workflow.get(True))  # YAML 1.1 boolean key
    assert "workflow_dispatch" in triggers
    assert "pull_request" in triggers and "main" in triggers["push"]["branches"]
    assert "*" in triggers["push"]["tags"]
    assert workflow["jobs"]["publish_pypi"]["if"] == (
        "startsWith(github.ref, 'refs/tags/') && !startsWith(github.ref, 'refs/tags/meeting-v')"
    )
    release_jobs = [
        job
        for name, job in workflow["jobs"].items()
        if name != "publish_pypi"
        and job.get("if") == "startsWith(github.ref, 'refs/tags/')"
    ]
    assert release_jobs, "Meeting tags must retain GitHub release artifact publication"
