"""Per-kind acquisition: git clone/pull, URL fetch, local adoption, video rejection."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from . import EfError
from .manifest import PROSE_SUFFIXES, VIDEO_SUFFIXES

VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "twitch.tv", "dailymotion.com")


def git(clone: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(clone), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise EfError(f"git {' '.join(args)} failed in {clone}: {result.stderr.strip()}")
    return result.stdout.strip()


def owner_repo(url: str) -> tuple[str, str]:
    """Split a git URL into owner and repo, matching graphify's clone cache layout.

    Only the path is considered, so a host is never mistaken for an owner.
    """
    cleaned = url.rstrip("/").removesuffix(".git")
    if "://" in cleaned:
        path = urlparse(cleaned).path
    elif ":" in cleaned:
        path = cleaned.split(":", 1)[1]  # scp-style: git@host:owner/repo
    else:
        path = cleaned
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise EfError(f"cannot derive owner/repo from {url!r}; expected .../<owner>/<repo>")
    return parts[-2], parts[-1]


def reject_video(target: str) -> None:
    """Raise on a video URL or path. Nothing else about video is built."""
    lowered = target.lower()
    if any(host in lowered for host in VIDEO_HOSTS) or Path(lowered).suffix in VIDEO_SUFFIXES:
        raise EfError(
            f"video is not supported yet: {target}\n"
            "Transcription needs graphify's video extra and prompt composition from "
            "corpus god nodes. Nothing was written to the pack."
        )


def clone(pack: Path, url: str) -> tuple[Path, str, str]:
    """Clone a git source to repos/<owner>/<repo>/. Returns (path, ref, rev)."""
    reject_video(url)
    owner, repo = owner_repo(url)
    target = pack / "repos" / owner / repo

    if target.is_dir():
        raise EfError(f"already present: {target.relative_to(pack)} (use `ef update` to refresh)")

    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", "--quiet", url, str(target)], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise EfError(f"clone failed: {result.stderr.strip()}")

    return (
        target,
        git(target, "rev-parse", "--abbrev-ref", "HEAD"),
        git(target, "rev-parse", "HEAD"),
    )


@dataclass
class Pull:
    path: str
    before: str
    after: str
    changed: list[str]

    @property
    def moved(self) -> bool:
        return self.before != self.after


def pull(pack: Path, entry: dict) -> Pull:
    """Fast-forward one refreshable source, refusing to discard local modifications."""
    target = pack / entry["path"]
    if not (target / ".git").is_dir():
        raise EfError(f"{entry['path']} is not a git checkout")

    dirty = git(target, "status", "--porcelain")
    if dirty:
        raise EfError(
            f"{entry['path']} has local modifications; refusing to refresh:\n"
            + "\n".join("  " + line for line in dirty.splitlines())
        )

    before = git(target, "rev-parse", "HEAD")
    git(target, "fetch", "--quiet", "origin")
    merge = subprocess.run(
        ["git", "-C", str(target), "merge", "--ff-only", "--quiet", "FETCH_HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if merge.returncode != 0:
        raise EfError(f"{entry['path']} cannot fast-forward; upstream history diverged")

    after = git(target, "rev-parse", "HEAD")
    changed: list[str] = []
    if before != after:
        prefix = entry["path"].rstrip("/")
        names = git(target, "diff", "--name-only", f"{before}..{after}")
        changed = [f"{prefix}/{name}" for name in names.splitlines() if name]

    return Pull(path=entry["path"], before=before, after=after, changed=changed)


def fetch(pack: Path, url: str, contributor: str | None) -> Path:
    """Fetch a page, paper or image into raw/, keeping graphify's provenance frontmatter."""
    reject_video(url)
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise EfError(f"not a fetchable URL: {url!r}")

    from graphify.ingest import ingest

    raw = pack / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    return ingest(url, raw, contributor=contributor)


def adopt_path(pack: Path, source: Path) -> list[Path]:
    """Copy a local file or directory into raw/ or notes/ by kind.

    Markdown goes to notes/ as authored prose; everything else is fetched-style
    material and lands in raw/, so the layout keeps the distinction visible.
    """
    source = source.expanduser().resolve()
    if not source.exists():
        raise EfError(f"no such path: {source}")

    files = (
        [source]
        if source.is_file()
        else sorted(p for p in source.rglob("*") if p.is_file() and not p.name.startswith("."))
    )
    if not files:
        raise EfError(f"nothing to adopt under {source}")

    for path in files:
        reject_video(str(path))

    adopted = []
    for path in files:
        layer = "notes" if path.suffix.lower() in PROSE_SUFFIXES else "raw"
        rel = path.name if source.is_file() else path.relative_to(source).as_posix()
        target = pack / layer / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        adopted.append(target)
    return adopted
