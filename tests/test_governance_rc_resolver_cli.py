from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT = SRC_ROOT / "governance" / "rc_resolver.py"
MODULE = [sys.executable, "-m", "governance.rc_resolver"]
DIRECT = [sys.executable, str(SCRIPT)]
SPEC_PATH = "governance/specification.jsonl"
TARGET = "src/governance/rc_resolver.py"


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_ROOT) if not existing else str(SRC_ROOT) + os.pathsep + existing
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _minimal_members() -> dict[str, bytes]:
    return {
        "src/governance/rc_resolver.py": (SRC_ROOT / "governance" / "rc_resolver.py").read_bytes(),
        "governance/specification.jsonl": (
            REPO_ROOT / "governance" / "specification.jsonl"
        ).read_bytes(),
        "governance/governance.jsonl": (REPO_ROOT / "governance" / "governance.jsonl").read_bytes(),
    }


def _write_minimal_snapshot(path: Path) -> None:
    members = _minimal_members()
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def _write_workspace_root(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for name, data in _minimal_members().items():
        dst = path / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)


def _run_resolver(
    cmd: list[str],
    *,
    cwd: Path,
    handoff: Path,
    pack: Path,
    digest: Path,
    snapshot: Path | None = None,
    workspace_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    args = [
        *cmd,
        TARGET,
        "--spec",
        SPEC_PATH,
        "--handoff-output",
        str(handoff),
        "--pack-output",
        str(pack),
        "--hash-output",
        str(digest),
    ]
    if workspace_root is not None:
        args.extend(["--workspace-root", str(workspace_root)])
    else:
        assert snapshot is not None
        args.extend(["--workspace-snapshot", str(snapshot)])
    return _run(args, cwd=cwd)


def test_rc_resolver_direct_script_help_from_outside_repo_cwd() -> None:
    proc = _run([*DIRECT, "--help"], cwd=Path("/tmp"))

    assert proc.returncode == 0, proc.stderr
    assert "usage:" in proc.stdout


def test_rc_resolver_direct_script_passes_from_outside_repo_cwd_with_workspace_root(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "patchhub"
    _write_workspace_root(workspace_root)

    handoff = tmp_path / "HANDOFF.md"
    pack = tmp_path / "constraint_pack.json"
    digest = tmp_path / "hash_pack.txt"
    proc = _run_resolver(
        DIRECT,
        cwd=Path("/tmp"),
        workspace_root=workspace_root,
        handoff=handoff,
        pack=pack,
        digest=digest,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "RESULT: PASS"


def test_rc_resolver_relocated_toolkit_passes_with_workspace_root(tmp_path: Path) -> None:
    toolkit_dir = tmp_path / "toolkit"
    toolkit_dir.mkdir()
    (toolkit_dir / "rc_resolver.py").write_bytes(
        (SRC_ROOT / "governance" / "rc_resolver.py").read_bytes()
    )
    (toolkit_dir / "workflow_effective_context.py").write_bytes(
        (SRC_ROOT / "governance" / "workflow_effective_context.py").read_bytes()
    )
    workspace_root = tmp_path / "patchhub"
    _write_workspace_root(workspace_root)

    proc = _run(
        [
            sys.executable,
            str(toolkit_dir / "rc_resolver.py"),
            TARGET,
            "--workspace-root",
            str(workspace_root),
            "--spec",
            SPEC_PATH,
            "--handoff-output",
            str(tmp_path / "HANDOFF.md"),
            "--pack-output",
            str(tmp_path / "constraint_pack.json"),
            "--hash-output",
            str(tmp_path / "hash_pack.txt"),
        ],
        cwd=Path("/tmp"),
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "RESULT: PASS"


def test_rc_resolver_direct_script_and_module_outputs_match(tmp_path: Path) -> None:
    snapshot = tmp_path / "patchhub-main_issue489.zip"
    _write_minimal_snapshot(snapshot)

    direct_handoff = tmp_path / "direct_HANDOFF.md"
    direct_pack = tmp_path / "direct_constraint_pack.json"
    direct_hash = tmp_path / "direct_hash_pack.txt"
    direct_proc = _run_resolver(
        DIRECT,
        cwd=REPO_ROOT,
        snapshot=snapshot,
        handoff=direct_handoff,
        pack=direct_pack,
        digest=direct_hash,
    )

    module_handoff = tmp_path / "module_HANDOFF.md"
    module_pack = tmp_path / "module_constraint_pack.json"
    module_hash = tmp_path / "module_hash_pack.txt"
    module_proc = _run_resolver(
        MODULE,
        cwd=REPO_ROOT,
        snapshot=snapshot,
        handoff=module_handoff,
        pack=module_pack,
        digest=module_hash,
    )

    assert direct_proc.returncode == 0, direct_proc.stderr
    assert module_proc.returncode == 0, module_proc.stderr
    assert direct_proc.stdout.strip() == "RESULT: PASS"
    assert module_proc.stdout.strip() == "RESULT: PASS"

    assert direct_pack.read_bytes() == module_pack.read_bytes()
    assert direct_hash.read_bytes() == module_hash.read_bytes()
    assert direct_handoff.read_text(encoding="utf-8") == module_handoff.read_text(encoding="utf-8")

    payload = direct_pack.read_bytes()
    assert direct_hash.read_text(encoding="utf-8") == hashlib.sha256(payload).hexdigest() + "\n"
    pack = json.loads(payload.decode("utf-8"))
    assert pack["target_scope"] == "implementation_scope"
    assert pack["mode"] == "final"
