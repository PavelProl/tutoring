"""Stage a v2 PDF pair, or accept the exact pair after explicit author review."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
from pathlib import Path
import shutil
import tempfile

from build_kit import build_kit, modern_identity, print_pdf, read_md

NAMES = ("Занятие.pdf", "Решения.pdf")


def pair_revision(folder):
    folder = Path(folder)
    if not folder.is_dir() or {p.name for p in folder.iterdir()} != set(NAMES):
        raise ValueError("expected exactly Занятие.pdf and Решения.pdf")
    digest = hashlib.sha256()
    for name in NAMES:
        path = folder / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("PDF must be a regular file")
        data = path.read_bytes()
        if not data.startswith(b"%PDF-") or len(data) < 20:
            raise ValueError(f"invalid PDF: {name}")
        digest.update(name.encode())
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


@contextmanager
def delivery_lock(root):
    build = Path(root) / "build"
    build.mkdir(exist_ok=True)
    with (build / ".delivery.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def replace_pair(source, target):
    """Copy/validate first, then swap directories; restore the old pair on failure."""
    source, target = Path(source), Path(target)
    revision = pair_revision(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("delivery directory cannot be a symlink")
    if target.exists():
        pair_revision(target)
    with tempfile.TemporaryDirectory(prefix=".delivery-", dir=target.parent) as temporary:
        temporary = Path(temporary)
        new, backup = temporary / "new", temporary / "previous"
        shutil.copytree(source, new)
        if pair_revision(new) != revision:
            raise ValueError("PDF pair changed while copying")
        had_previous = target.exists()
        if had_previous:
            target.rename(backup)
        try:
            new.rename(target)
        except BaseException:
            if had_previous:
                backup.rename(target)
            raise
    return revision


def delivery_folder(content_root, source, workspace):
    kit, _ = read_md(Path(content_root) / source)
    if kit.get("format_version") != 2:
        raise ValueError("delivery is available only for format_version: 2")
    return Path(workspace) / "Занятия", modern_identity(kit)


def stage(content_root, source, workspace, *, review_requested=False):
    content_root = Path(content_root).resolve()
    base, folder = delivery_folder(content_root, source, workspace)
    pages = build_kit(content_root, content_root / source, review_requested=review_requested)
    if len(pages) != 2 or {p.name for _, p in pages} != set(NAMES):
        raise ValueError("v2 delivery requires exactly two outputs")
    with delivery_lock(content_root), tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        pair = temporary / "pair"
        pair.mkdir()
        for text, pdf in pages:
            print_pdf(text, pair / pdf.name, temporary)
        revision = replace_pair(pair, base / "На проверку" / folder)
    return base / "На проверку" / folder, revision


def accept(content_root, source, workspace, *, revision, author_approved=False):
    if not author_approved:
        raise ValueError("explicit author approval is required")
    content_root = Path(content_root).resolve()
    base, folder = delivery_folder(content_root, source, workspace)
    draft, ready = base / "На проверку" / folder, base / "Готово" / folder
    with delivery_lock(content_root):
        if pair_revision(draft) != revision:
            raise ValueError("draft differs from the reviewed revision; author must review it again")
        replace_pair(draft, ready)
        shutil.rmtree(draft)
    return ready


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "accept"))
    parser.add_argument("content_root", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("--workspace", required=True, type=Path, help="chemistry root, including when run from a worktree")
    parser.add_argument("--review-requested", action="store_true")
    parser.add_argument("--author-approved", action="store_true")
    parser.add_argument("--revision", help="SHA-256 printed when the author-reviewed draft was staged")
    args = parser.parse_args()
    try:
        if args.action == "stage":
            path, revision = stage(args.content_root, args.source, args.workspace.resolve(), review_requested=args.review_requested)
            for name in NAMES:
                print(path / name)
            print(f"Revision: {revision}")
        else:
            if not args.revision:
                parser.error("accept requires --revision")
            path = accept(args.content_root, args.source, args.workspace.resolve(), revision=args.revision,
                          author_approved=args.author_approved)
            for name in NAMES:
                print(path / name)
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
