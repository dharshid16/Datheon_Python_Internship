"""
Smart File Organizer & Cleanup Utility
======================================

Sorts the files in a folder (for example Downloads) into category subfolders
such as Documents, Images, Videos, Archives and Code, based on file extension.

Features
--------
* Colour-coded live output and a summary table with file counts, sizes and bars
* --dry-run   preview every move without touching a single file
* --undo      put the files from the last run back where they were
* --by-date   optional sub-folders by month, e.g. Images/2026-11
* Naming collisions are resolved by renaming (report.pdf -> report_1.pdf)
* PermissionError / OSError are caught and logged; one bad file never stops the run
* Sub-folders, hidden files, unfinished downloads and this script are never moved
* Every action is written to organizer.log; moves are saved for undo

Usage
-----
    python organizer.py "C:\\Users\\you\\Downloads" --dry-run
    python organizer.py "C:\\Users\\you\\Downloads"
    python organizer.py "C:\\Users\\you\\Downloads" --by-date
    python organizer.py "C:\\Users\\you\\Downloads" --undo
"""

import argparse
import json
import logging
import os
import shutil
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
CATEGORIES = {
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls",
                  ".xlsx", ".csv", ".ppt", ".pptx", ".md"},
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff"},
    "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "Code": {".py", ".js", ".html", ".css", ".java", ".c", ".cpp", ".json",
             ".ts", ".sql", ".sh", ".ipynb"},
}
DEFAULT_CATEGORY = "Others"
SKIP_EXTENSIONS = {".crdownload", ".part", ".tmp", ".download"}  # unfinished downloads
LOG_FILE = "organizer.log"
HISTORY_FILE = ".organizer_history.json"

# extension -> category lookup built once from CATEGORIES
EXTENSION_MAP = {ext: cat for cat, exts in CATEGORIES.items() for ext in exts}

ICONS = {"Documents": "📄", "Images": "🖼 ", "Videos": "🎬", "Archives": "📦",
         "Code": "💻", "Others": "📁"}

# ──────────────────────────────────────────────
# Colour helpers (ANSI) - disabled when unsupported
# ──────────────────────────────────────────────
USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
if USE_COLOR and os.name == "nt":
    os.system("")  # enables ANSI escape handling on Windows terminals

GREEN, RED, YELLOW, CYAN, DIM, BOLD = "32", "31", "33", "36", "2", "1"


def paint(text: str, code: str) -> str:
    """Wrap text in an ANSI colour code if colour output is enabled."""
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


class ConsoleFormatter(logging.Formatter):
    """Console formatter that colours a line using the record's `style` attribute."""

    def format(self, record: logging.LogRecord) -> str:
        line = f"{datetime.fromtimestamp(record.created):%H:%M:%S}  {record.getMessage()}"
        style = getattr(record, "style", None)
        return paint(line, style) if style else line


logger = logging.getLogger("organizer")


# ──────────────────────────────────────────────
# Core helpers (pure functions - easy to test)
# ──────────────────────────────────────────────
def get_category(filename: str) -> str:
    """Return the category folder name for a file, based on its extension."""
    return EXTENSION_MAP.get(Path(filename).suffix.lower(), DEFAULT_CATEGORY)


def human_size(num_bytes: float) -> str:
    """Format a byte count as a readable string, e.g. 1.5 MB."""
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GB"


def unique_destination(folder: Path, filename: str) -> Path:
    """Return a path in `folder` that does not exist yet.

    If 'report.pdf' is taken, tries 'report_1.pdf', 'report_2.pdf', ...
    """
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem, suffix = Path(filename).stem, Path(filename).suffix
    counter = 1
    while True:
        candidate = folder / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def should_skip(entry: os.DirEntry, script_name: Optional[str]) -> Optional[str]:
    """Return a reason to skip this directory entry, or None if it should be moved."""
    if not entry.is_file(follow_symlinks=False):
        return "not a regular file"
    if entry.name.startswith("."):
        return "hidden file"
    if Path(entry.name).suffix.lower() in SKIP_EXTENSIONS:
        return "unfinished download"
    if entry.name in (LOG_FILE, script_name):
        return "organizer's own file"
    return None


def destination_folder(target: Path, category: str, mtime: float, by_date: bool) -> Path:
    """Folder a file belongs in, optionally with a YYYY-MM sub-folder."""
    folder = target / category
    if by_date:
        folder = folder / datetime.fromtimestamp(mtime).strftime("%Y-%m")
    return folder


# ──────────────────────────────────────────────
# History (for --undo)
# ──────────────────────────────────────────────
def load_history(target: Path) -> list:
    """Read the saved list of previous runs (empty list if none or unreadable)."""
    try:
        with open(target / HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_history(target: Path, history: list) -> None:
    """Write the run history; remove the file when it is empty."""
    path = target / HISTORY_FILE
    try:
        if history:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        elif path.exists():
            path.unlink()
    except OSError as exc:
        logger.error("Could not save undo history: %s", exc, extra={"style": RED})


# ──────────────────────────────────────────────
# Main routines
# ──────────────────────────────────────────────
def organize(target: Path, dry_run: bool = False, by_date: bool = False) -> dict:
    """Organise the files directly inside `target`.

    Returns a summary dict with keys:
        moved (Counter category -> files), sizes (Counter category -> bytes),
        skipped (int), errors (int), moves (list of [source, destination]).
    """
    summary = {"moved": Counter(), "sizes": Counter(), "skipped": 0, "errors": 0, "moves": []}
    script_name = Path(__file__).name

    try:
        entries = sorted(os.scandir(target), key=lambda e: e.name.lower())
    except OSError as exc:
        logger.error("Cannot read folder %s: %s", target, exc, extra={"style": RED})
        summary["errors"] += 1
        return summary

    for entry in entries:
        reason = should_skip(entry, script_name)
        if reason:
            if entry.is_file(follow_symlinks=False):
                logger.info("⏭  SKIPPED  %s (%s)", entry.name, reason, extra={"style": DIM})
                summary["skipped"] += 1
            continue

        try:
            stat = entry.stat()
            category = get_category(entry.name)
            folder = destination_folder(target, category, stat.st_mtime, by_date)
            if not dry_run:
                folder.mkdir(parents=True, exist_ok=True)
            destination = unique_destination(folder, entry.name)
            shown = destination.relative_to(target).as_posix()
            if dry_run:
                logger.info("👀 WOULD MOVE  %s  →  %s", entry.name, shown, extra={"style": CYAN})
            else:
                shutil.move(entry.path, str(destination))
                logger.info("✔  MOVED  %s  →  %s", entry.name, shown, extra={"style": GREEN})
                summary["moves"].append([entry.path, str(destination)])
            summary["moved"][category] += 1
            summary["sizes"][category] += stat.st_size
        except PermissionError:
            logger.error("✘  PERMISSION DENIED  %s (file may be open or protected)",
                         entry.name, extra={"style": RED})
            summary["errors"] += 1
        except FileExistsError:
            logger.error("✘  ALREADY EXISTS  %s", entry.name, extra={"style": RED})
            summary["errors"] += 1
        except OSError as exc:
            logger.error("✘  FAILED  %s: %s", entry.name, exc, extra={"style": RED})
            summary["errors"] += 1

    return summary


def undo_last_run(target: Path, dry_run: bool = False) -> dict:
    """Move the files of the most recent run back to their original place."""
    summary = {"restored": 0, "missing": 0, "errors": 0}
    history = load_history(target)
    if not history:
        logger.info("Nothing to undo in this folder.", extra={"style": YELLOW})
        return summary

    run = history[-1]
    for source, destination in reversed(run["moves"]):
        src, dst = Path(source), Path(destination)
        if not dst.exists():
            logger.info("⚠  MISSING  %s (moved or deleted since)", dst.name, extra={"style": YELLOW})
            summary["missing"] += 1
            continue
        try:
            restore_to = unique_destination(src.parent, src.name)
            if dry_run:
                logger.info("👀 WOULD RESTORE  %s  →  %s", dst.name, restore_to.name,
                            extra={"style": CYAN})
            else:
                shutil.move(str(dst), str(restore_to))
                logger.info("↩  RESTORED  %s", restore_to.name, extra={"style": GREEN})
            summary["restored"] += 1
        except OSError as exc:
            logger.error("✘  FAILED  %s: %s", dst.name, exc, extra={"style": RED})
            summary["errors"] += 1

    if not dry_run:
        remove_empty_folders(target)
        if summary["errors"] == 0:
            save_history(target, history[:-1])
    return summary


def remove_empty_folders(target: Path) -> None:
    """Delete empty category (and date) folders left behind after an undo."""
    for category in list(CATEGORIES) + [DEFAULT_CATEGORY]:
        base = target / category
        if not base.is_dir():
            continue
        for folder in sorted(base.rglob("*"), reverse=True):
            if folder.is_dir():
                try:
                    folder.rmdir()
                except OSError:
                    pass
        try:
            base.rmdir()
        except OSError:
            pass


# ──────────────────────────────────────────────
# Reporting
# ──────────────────────────────────────────────
def print_banner(target: Path, mode: str) -> None:
    print()
    print(paint("╔" + "═" * 46 + "╗", CYAN))
    print(paint("║" + "SMART FILE ORGANIZER".center(46) + "║", CYAN))
    print(paint("╚" + "═" * 46 + "╝", CYAN))
    print(f"  Folder : {target}")
    print(f"  Mode   : {mode}\n")


def print_summary(summary: dict, dry_run: bool, elapsed: float) -> None:
    """Print a formatted execution summary table with bars."""
    total = sum(summary["moved"].values())
    total_size = sum(summary["sizes"].values())
    verb = "Would move" if dry_run else "Moved"
    width = 20

    print()
    print(paint("  SUMMARY" + ("  (dry run - nothing was changed)" if dry_run else ""), BOLD))
    print("  " + "─" * 58)
    print(f"  {'Category':<14}{'Files':>6}{'Size':>11}   Share")
    print("  " + "─" * 58)
    for category in sorted(summary["moved"], key=lambda c: -summary["moved"][c]):
        count = summary["moved"][category]
        bar = "█" * max(1, round(width * count / total))
        label = f"{ICONS.get(category, '📁')} {category}"
        print(f"  {label:<14}{count:>6}{human_size(summary['sizes'][category]):>11}   "
              f"{paint(bar, GREEN)}")
    print("  " + "─" * 58)
    print(f"  {verb + ':':<14}{total:>6}{human_size(total_size):>11}")
    print(f"  {'Skipped:':<14}{summary['skipped']:>6}")
    errors = summary["errors"]
    print(f"  {'Errors:':<14}{paint(str(errors), RED if errors else GREEN):>6}")
    print(f"  {'Time:':<14}{elapsed:>5.2f}s")
    print()


def print_undo_summary(summary: dict, dry_run: bool) -> None:
    verb = "Would restore" if dry_run else "Restored"
    print()
    print(paint("  UNDO SUMMARY", BOLD))
    print("  " + "─" * 30)
    print(f"  {verb + ':':<16}{summary['restored']:>5}")
    print(f"  {'Missing:':<16}{summary['missing']:>5}")
    print(f"  {'Errors:':<16}{summary['errors']:>5}")
    print()


def setup_logging(target: Path, dry_run: bool) -> None:
    """Log to the console and (unless dry-run) to organizer.log inside the target."""
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ConsoleFormatter())
    logger.addHandler(console)
    if not dry_run:
        try:
            file_handler = logging.FileHandler(target / LOG_FILE, encoding="utf-8")
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
            logger.addHandler(file_handler)
        except OSError:
            pass  # logging to file is optional


def close_logging() -> None:
    """Close every log handler so organizer.log is released (required on Windows)."""
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def main(argv: Optional[list] = None) -> int:
    """Parse arguments, run the organiser and always release the log file."""
    try:
        return _run(argv)
    finally:
        close_logging()


def _run(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Organise a folder by file type.")
    parser.add_argument("folder", help="path of the folder to organise")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would happen without moving anything")
    parser.add_argument("--by-date", action="store_true",
                        help="add month sub-folders, e.g. Images/2026-11")
    parser.add_argument("--undo", action="store_true",
                        help="restore the files moved by the last run")
    args = parser.parse_args(argv)

    target = Path(args.folder).expanduser().resolve()
    if not target.is_dir():
        print(f"Error: '{target}' is not a folder.")
        return 1

    setup_logging(target, args.dry_run)

    if args.undo:
        print_banner(target, "UNDO last run" + (" (dry run)" if args.dry_run else ""))
        print_undo_summary(undo_last_run(target, args.dry_run), args.dry_run)
        return 0

    mode = ("DRY RUN (preview only)" if args.dry_run else "ORGANISE") + \
           (" + by date" if args.by_date else "")
    print_banner(target, mode)

    start = time.perf_counter()
    summary = organize(target, args.dry_run, args.by_date)
    elapsed = time.perf_counter() - start

    if summary["moves"]:
        history = load_history(target)
        history.append({"time": datetime.now().isoformat(timespec="seconds"),
                        "moves": summary["moves"]})
        save_history(target, history)

    print_summary(summary, args.dry_run, elapsed)
    if summary["moves"]:
        print(paint("  Tip: run again with --undo to put everything back.\n", DIM))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted. Goodbye!")
        sys.exit(130)