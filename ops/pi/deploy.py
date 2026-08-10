#!/usr/bin/env python3
"""Repo-first Pi deployment over SSH.

- Bundles this repo while excluding local heavy/generated directories.
- Uploads archive to remote host via scp.
- Extracts into remote project path.
- Optionally runs cleanup for non-essential services.
- Runs provision script to apply service and nginx from repo.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

EXCLUDES = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "site-packages",
    ".pytest_cache",
}


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def should_include(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root)
    parts = set(rel.parts)
    return not any(part in EXCLUDES for part in parts)


def build_archive(repo_root: Path) -> Path:
    fd, tmp_name = tempfile.mkstemp(prefix="py_app_", suffix=".tar.gz")
    os.close(fd)
    archive_path = Path(tmp_name)

    with tarfile.open(archive_path, "w:gz") as tar:
        for path in repo_root.rglob("*"):
            if not should_include(path, repo_root):
                continue
            rel = path.relative_to(repo_root)
            tar.add(path, arcname=str(rel), recursive=False)
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy py_app to Raspberry Pi over SSH")
    parser.add_argument("--ssh-target", default="rpi3",
                        help="SSH host alias (default: rpi3)")
    parser.add_argument(
        "--project-path",
        default="/home/neulas/projects/py_app",
        help="Remote project path",
    )
    parser.add_argument(
        "--cleanup-nonessential",
        action="store_true",
        help="Run remote cleanup_nonessential.sh (headscale + wg0)",
    )
    parser.add_argument(
        "--purge-headscale",
        action="store_true",
        help="When cleanup is enabled, purge headscale package too",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Fast deploy mode: skip apt refresh and heavy dependency reinstall",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    archive_path = build_archive(repo_root)
    remote_archive = "/tmp/py_app_bundle.tar.gz"

    try:
        run(["ssh", args.ssh_target, f"mkdir -p {args.project_path}"])
        run(["scp", str(archive_path), f"{args.ssh_target}:{remote_archive}"])
        run(
            [
                "ssh",
                args.ssh_target,
                (
                    f"tar -xzf {remote_archive} -C {args.project_path} "
                    "&& rm -f /tmp/py_app_bundle.tar.gz "
                    f"&& chmod +x {args.project_path}/ops/pi/*.sh"
                ),
            ]
        )

        if args.cleanup_nonessential:
            cleanup_arg = "purge-headscale" if args.purge_headscale else "no"
            run(
                [
                    "ssh",
                    args.ssh_target,
                    f"bash {args.project_path}/ops/pi/cleanup_nonessential.sh {cleanup_arg}",
                ]
            )

        run(
            [
                "ssh",
                args.ssh_target,
                (
                    f"bash {args.project_path}/ops/pi/provision_remote.sh "
                    f"{args.project_path} {'quick' if args.quick else 'full'}"
                ),
            ]
        )

        run(
            [
                "ssh",
                args.ssh_target,
                f"bash {args.project_path}/ops/pi/statuscheck_remote.sh",
            ]
        )
    finally:
        archive_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
