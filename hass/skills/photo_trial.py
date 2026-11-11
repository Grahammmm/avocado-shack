"""AV1109-10 (SKILLS-PIC-3, card 16): offline real-photo trial harness for the house picture render.

    python3 hass/skills/photo_trial.py DIR [--json]

Runs every JPEG/PNG (``.jpg``, ``.jpeg``, ``.png``, any letter case) directly inside DIR through the house render
(``hass.newitem_render.render``), the house-style check (``hass.house_style.check_image`` on the rendered picture) and the
retake advice item.picture gives (``hass.skills.item_picture.picture_review``), and prints one row per photo:

    Photo<TAB>Result<TAB>Failing checks<TAB>Retake advice        (text; ``--json``: one JSON array of the same rows)

``Result`` is ``pass`` or ``warn``. A photo warns when a house-style check fails, the render has a warning, or the advice
has a retake sentence; a clean pass has no advice. The advice is item.picture's own wording, never a copy.

Read-only and external-only:
* DIR must be an existing directory OUTSIDE this repository, not a symlink and not reached through a symlink. It is
  opened once, component by component without following links, and that held descriptor serves the listing and every
  photo read, so replacing the folder's name afterwards cannot redirect the trial. It is read one level deep (no recursion); other files and subfolders are skipped. A symbolic-link photo refuses the whole run before
  any file is read. A folder with no JPEG/PNG is a usage refusal, not a pass.
* Output is stdout only. There is no output-file option. When stdout is a regular file inside the repository the run is
  refused before anything is written (a terminal, a pipe or an outside file is fine). A shell redirect opens and truncates
  its target before Python starts, so this tool cannot undo it: redirect only to a path outside the repository.
* Nothing is installed, committed, published or sent; no network. Rendered pictures stay in memory and are dropped. EXIF,
  GPS, device and time tags, pixels and the DIR path are never printed. An unreadable or undecodable photo is a ``warn`` row
  with a fixed code and sentence, and the run continues.

Exit codes: 0 every photo passes, 1 the run finished and at least one photo warns, 2 usage, path, sink or setup failure
(stderr only, no traceback, no partial output).

Automated tests use only the synthetic photos of hass/newitem_synthetic.py; running this on real photos is an operator step.
"""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SUFFIXES = (".jpg", ".jpeg", ".png")
HEADER = "Photo\tResult\tFailing checks\tRetake advice"
UNREADABLE, CANNOT_RENDER = "unreadable-photo", "cannot-render"
UNREADABLE_SAY = "I couldn't read this photo. Send it again as a JPEG or PNG."


FOLDER_UNREADABLE = "The photo folder cannot be read (no permission, or a file system error). Nothing was read."


class TrialError(Exception):
    """A usage, path, sink or setup refusal. ``str(exc)`` is a fixed, safe sentence (no path, no exception text)."""


def _inside_repo(path: Path) -> bool:
    root = REPO_ROOT.resolve()
    return path == root or root in path.parents


def checked_directory(arg: str) -> Path:
    """DIR as a symlink-free absolute path, or TrialError. Every component is checked on the way down."""
    fd, path = _open_directory(arg)
    os.close(fd)
    return path


_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_LINK_SAY = "The photo folder is a symbolic link, or is reached through one. Give the real folder."


def _open_directory(arg: str) -> tuple:
    """(directory descriptor, absolute path) of DIR. The descriptor is the admitted folder: later listing and reads go
    through it, never through the pathname again, so renaming or replacing the name afterwards cannot redirect them.
    The caller closes the descriptor. Raises TrialError (fixed, path-free sentences)."""
    if not arg:
        raise TrialError("Give the folder of photos to try.")
    try:
        return _walk_directory(arg)
    except OSError:  # permission, loop or I/O error: say so without the path the system error carries
        raise TrialError(FOLDER_UNREADABLE) from None


def _open_component(parent_fd: int, part: str) -> int:
    try:
        return os.open(part, _DIR_FLAGS, dir_fd=parent_fd)  # non-following: a link (even one swapped in just now) is refused
    except OSError:
        try:
            kind = os.stat(part, dir_fd=parent_fd, follow_symlinks=False).st_mode
        except FileNotFoundError:
            raise TrialError("That folder does not exist.") from None
        if stat.S_ISLNK(kind):
            raise TrialError(_LINK_SAY) from None
        if not stat.S_ISDIR(kind):
            raise TrialError("That is not a folder.") from None
        raise


def _walk_directory(arg: str) -> tuple:
    raw = Path(arg)
    fd = os.open(raw.anchor if raw.is_absolute() else ".", _DIR_FLAGS)  # the working directory is already a real path
    try:
        for part in raw.parts[1:] if raw.is_absolute() else raw.parts:
            if part == ".":
                continue
            nxt = _open_component(fd, part)  # ".." is the real parent: every earlier component is a held non-link directory
            os.close(fd)
            fd = nxt
        cur = Path(os.readlink(f"/proc/self/fd/{fd}"))  # where the held descriptor really is, checked before any photo read
        if _inside_repo(cur):
            raise TrialError("The photo folder is inside the repository. Use a folder outside it.")
        return fd, cur
    except BaseException:
        os.close(fd)
        raise


def candidates(directory) -> list:
    """Sorted (name, path) of the JPEG/PNG regular files directly in DIR (a path, or the held descriptor from
    _open_directory). Refuses link candidates before any read."""
    found = []
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if os.path.splitext(entry.name)[1].lower() not in SUFFIXES:
                    continue
                if entry.is_symlink():
                    raise TrialError("A photo in the folder is a symbolic link. Nothing was read.")
                if entry.is_file(follow_symlinks=False):
                    found.append((entry.name, Path(entry.name) if isinstance(directory, int) else Path(entry.path)))
    except OSError:  # unreadable folder: a fixed refusal, never the system error that names the path
        raise TrialError(FOLDER_UNREADABLE) from None
    found.sort(key=lambda item: item[0])
    if not found:
        raise TrialError("There is no JPEG or PNG photo in that folder.")
    return found


def sink_problem(stream) -> str:
    """A refusal sentence when the output stream is a regular file inside the repository (or cannot be told), else ''."""
    try:
        fd = stream.fileno()
    except (AttributeError, OSError, ValueError):
        return ""  # an in-memory stream: no file is written
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return ""  # a terminal, pipe or socket
        target = Path(os.readlink(f"/proc/self/fd/{fd}")).resolve()
    except (OSError, ValueError):
        return "I can't tell where the output is going, so I stopped. Print to the terminal or to a file outside the repository."
    return "The output is going to a file inside the repository. Send it to a file outside the repository." if _inside_repo(target) else ""


def _read_photo(path: Path, dir_fd=None) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("not a regular file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(fd)


def _tools():
    """The project modules, imported only when a trial runs (importing this file stays inert)."""
    from hass import house_style, newitem_render  # noqa: PLC0415
    from hass.skills.item_picture import picture_review  # noqa: PLC0415 - the AV1109-05 handover
    return house_style, newitem_render, picture_review


def _row(name: str, status: str, failed: list, advice: list) -> dict:
    return {"file": name, "status": status, "failed_checks": failed, "advice": advice}


def assess_photo(name: str, data: bytes) -> dict:
    """One closed row {file, status, failed_checks, advice}. PillowMissing/ImportError propagate (a setup error)."""
    house_style, newitem_render, picture_review = _tools()
    try:
        rendered = newitem_render.render(data)
    except (house_style.PillowMissing, ImportError):
        raise
    except Exception:  # noqa: BLE001 - a photo the renderer refuses or cannot decode is one fixed row, never a crash
        return _row(name, "warn", [CANNOT_RENDER], [UNREADABLE_SAY])
    check = house_style.check_image(rendered["jpeg"])
    failed = [c["name"] for c in check["checks"] if not c.get("ok")]
    _, warn = picture_review(data, True)
    advice = list(warn)
    review = list(rendered["report"].get("review") or [])
    if (review or not check["pass"]) and not advice:
        raise TrialError("The picture advice did not match the render result, so I stopped.")
    return _row(name, "warn" if failed or review or advice else "pass", failed, advice)


def trial_directory(directory) -> list:
    """Rows for every candidate photo in DIR (the held descriptor from _open_directory, or a path that is admitted
    again), in filename order. Photos are opened relative to the descriptor, never by rebuilt pathname."""
    if not isinstance(directory, int):
        fd, _ = _open_directory(str(directory))
        try:
            return trial_directory(fd)
        finally:
            os.close(fd)
    rows = []
    for name, path in candidates(directory):
        try:
            data = _read_photo(path, dir_fd=directory)
        except OSError:
            try:
                is_link = stat.S_ISLNK(os.stat(name, dir_fd=directory, follow_symlinks=False).st_mode)
            except OSError:
                is_link = False
            if is_link:  # swapped for a link after listing: refuse the whole run, nothing was printed yet
                raise TrialError("A photo in the folder is a symbolic link. Nothing was read.") from None
            rows.append(_row(name, "warn", [UNREADABLE], [UNREADABLE_SAY]))
            continue
        rows.append(assess_photo(name, data))
    return rows


def format_text(rows: list) -> str:
    def clean(text):
        return " ".join(str(text).split())
    lines = [HEADER]
    for row in rows:
        lines.append("\t".join((json.dumps(row["file"], ensure_ascii=True)[1:-1], row["status"],
                                ";".join(clean(c) for c in row["failed_checks"]) or "-",
                                " ".join(clean(a) for a in row["advice"]) or "-")))
    return "\n".join(lines) + "\n"


def format_json(rows: list) -> str:
    return json.dumps(rows, ensure_ascii=True) + "\n"


def _parse(argv: list) -> tuple:
    import argparse  # noqa: PLC0415

    class Parser(argparse.ArgumentParser):
        def error(self, message):  # the message names the bad option, never a path
            raise TrialError("Usage: python3 hass/skills/photo_trial.py DIR [--json]")

    parser = Parser(prog="photo_trial.py", add_help=False, allow_abbrev=False)
    parser.add_argument("dir")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    return args.dir, args.json


def main(argv=None, stdout=None, stderr=None) -> int:
    out, err = stdout or sys.stdout, stderr or sys.stderr
    try:
        arg, as_json = _parse(list(sys.argv[1:] if argv is None else argv))
        problem = sink_problem(out)
        if problem:
            raise TrialError(problem)
        dir_fd, _ = _open_directory(arg)
        try:
            candidates(dir_fd)  # refuse an empty folder or a link before any tool is imported or any file read
            rows = trial_directory(dir_fd)
        except ImportError:  # includes house_style.PillowMissing's siblings and a missing advice helper
            raise TrialError("The picture tools are not available here (Pillow or the item.picture helper), so I stopped.") from None
        except RuntimeError as exc:  # house_style.PillowMissing
            if type(exc).__name__ != "PillowMissing":
                raise
            raise TrialError("Pillow is not installed here, so the pictures can't be checked.") from None
        finally:
            os.close(dir_fd)
    except TrialError as exc:
        print(f"photo_trial: {exc}", file=err)
        return 2
    out.write(format_json(rows) if as_json else format_text(rows))
    out.flush()
    return 1 if any(row["status"] != "pass" for row in rows) else 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True  # a plain run must leave no __pycache__ inside the repository
    sys.path[:] = [str(REPO_ROOT)] + [p for p in sys.path if os.path.realpath(p or ".") != str(Path(__file__).resolve().parent)]
    raise SystemExit(main())
