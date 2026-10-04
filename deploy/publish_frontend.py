#!/usr/bin/env python3
"""Publish a built frontend as a versioned release with shared hashed assets.

`<site-root>/assets` is shared by every release, so a page that was already
loaded keeps resolving its hashed JS/CSS after `current` moves to a new build.
Everything else (HTML and public example files) stays inside its own release
and is still served from `<site-root>/current`. Existing assets and release
directories are never overwritten.

Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path

DEFAULT_SITE_ROOT = Path("/var/www/endfield-workbench")
RELEASE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
ASSETS = "assets"
CHUNK = 1 << 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_directory(path: Path) -> None:
    """Create missing directories with mode 0755; existing ones are left alone."""
    missing: list[Path] = []
    probe = path
    while not os.path.lexists(probe):
        missing.append(probe)
        probe = probe.parent
    for directory in reversed(missing):
        os.mkdir(directory, 0o755)
        os.chmod(directory, 0o755)


def scan(root: Path, label: str) -> dict[str, str]:
    """Hash every regular file below root, rejecting symlinks and specials."""
    if root.is_symlink() or not root.is_dir():
        raise SystemExit(f"{label}: not a regular directory: {root}")
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise SystemExit(f"{label}: symlink is not allowed: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise SystemExit(f"{label}: not a regular file: {relative}")
        files[relative] = sha256(path)
    return files


def assets_of(root: Path, label: str) -> dict[str, str]:
    """Hash the files under <root>/assets, rejecting symlinks and specials."""
    directory = root / ASSETS
    if not os.path.lexists(directory):
        return {}
    if directory.is_symlink() or not directory.is_dir():
        raise SystemExit(f"{label}: assets is not a regular directory: {directory}")
    files: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():
            raise SystemExit(f"{label}: symlink is not allowed: {ASSETS}/{relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise SystemExit(f"{label}: not a regular file: {ASSETS}/{relative}")
        files[relative] = sha256(path)
    return files


def verify_reuse(destination: Path, expected: Path) -> None:
    """Accept an existing asset only as a regular file with the planned content."""
    if destination.is_symlink() or not destination.is_file():
        raise SystemExit(f"shared asset is not a regular file: {destination}")
    if destination != expected and sha256(destination) != sha256(expected):
        raise SystemExit(f"shared asset content differs from the build: {destination}")


def install(source: Path, destination: Path) -> None:
    """Copy one content-addressed asset without ever replacing an existing file."""
    make_directory(destination.parent)
    handle, temporary = tempfile.mkstemp(prefix=".publish-", dir=destination.parent)
    os.close(handle)
    temporary_path = Path(temporary)
    try:
        shutil.copyfile(source, temporary_path)
        os.chmod(temporary_path, 0o644)
        try:
            os.link(temporary_path, destination)
        except FileExistsError:
            # A concurrent publish created the path: reuse it only after the same
            # regular-file and content checks, and fail before `current` switches.
            verify_reuse(destination, temporary_path)
    finally:
        temporary_path.unlink()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", type=Path, default=DEFAULT_SITE_ROOT)
    parser.add_argument("--dist", type=Path, default=project_root / "web" / "dist")
    parser.add_argument("--release", required=True, help="safe release directory name")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not RELEASE_NAME.fullmatch(args.release):
        raise SystemExit(f"unsafe release name: {args.release!r}")

    site_root = args.site_root.resolve()
    if not site_root.is_dir():
        raise SystemExit(f"site root does not exist: {site_root}")
    dist = args.dist.resolve()
    releases = site_root / "releases"
    assets_dir = site_root / ASSETS
    release_dir = releases / args.release
    current = site_root / "current"
    staging = site_root / "current.next"

    # `<site-root>/releases` is created at most once here; a symlink or a plain
    # file would send the new release outside the site root.
    if os.path.lexists(releases):
        if releases.is_symlink() or not releases.is_dir():
            raise SystemExit(f"releases is not a regular directory: {releases}")
    else:
        make_directory(releases)

    if os.path.lexists(release_dir):
        raise SystemExit(f"release already exists: {release_dir}")
    if os.path.lexists(staging):
        raise SystemExit(f"staging symlink already exists, remove it first: {staging}")
    if current.is_symlink():
        linked = Path(os.readlink(current))
        old_target = linked if linked.is_absolute() else site_root / linked
    elif os.path.lexists(current):
        raise SystemExit(f"current exists but is not a symlink: {current}")
    else:
        old_target = None

    # Validate every retained release, the shared directory, and the new build
    # before writing anything. Same name with a different digest is fatal.
    sources: list[tuple[str, Path, dict[str, str]]] = []
    if os.path.lexists(assets_dir):
        sources.append(("shared assets", assets_dir, assets_of(site_root, "shared assets")))
    for entry in sorted(releases.iterdir()):
        if entry.is_symlink():
            raise SystemExit(f"releases: symlink is not allowed: {entry.name}")
        if entry.is_dir():
            sources.append((f"release {entry.name}", entry / ASSETS, assets_of(entry, f"release {entry.name}")))
    dist_files = scan(dist, "dist")
    if "index.html" not in dist_files:
        raise SystemExit(f"dist has no index.html: {dist}")
    sources.append(("dist", dist / ASSETS, assets_of(dist, "dist")))

    plan: dict[str, Path] = {}
    owners: dict[str, tuple[str, str]] = {}
    conflicts: list[str] = []
    for label, directory, files in sources:
        for name, value in files.items():
            previous = owners.get(name)
            if previous is None:
                owners[name] = (value, label)
                plan[name] = directory / name
            elif previous[0] != value:
                conflicts.append(f"{name}: {previous[1]} {previous[0][:12]} vs {label} {value[:12]}")
    if conflicts:
        raise SystemExit("asset collision, nothing written:\n  " + "\n  ".join(sorted(conflicts)))

    # Import historical assets and install the new build's assets first.
    installed = reused = 0
    for name in sorted(plan):
        destination = assets_dir / name
        if os.path.lexists(destination):
            verify_reuse(destination, plan[name])
            reused += 1
        else:
            install(plan[name], destination)
            installed += 1
    print(f"assets: {installed} installed, {reused} reused, {len(plan)} referenced")

    # Build the complete release, then switch `current` with one rename.
    os.mkdir(release_dir, 0o755)  # never reuse an existing release directory
    os.chmod(release_dir, 0o755)
    try:
        shutil.copytree(dist, release_dir, dirs_exist_ok=True, symlinks=False)
        if scan(release_dir, "new release") != dist_files:
            raise SystemExit(f"release copy is incomplete: {release_dir}")
    except BaseException:
        shutil.rmtree(release_dir, ignore_errors=True)
        raise

    os.symlink(str(release_dir), staging)
    try:
        os.replace(staging, current)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise

    print(f"release: {release_dir}")
    print(f"current: {old_target or '(none)'} -> {release_dir}")
    if old_target is not None:
        print(f"rollback: ln -sfn {old_target} {staging} && mv -Tf {staging} {current}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
