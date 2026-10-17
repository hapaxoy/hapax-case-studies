"""Lock and unlock the held-out material while agent runs are going, so an agent with a shell cannot read it.

    python code/lock_answers.py lock    [--extended] [--with-code]
    python code/lock_answers.py status  [--require-locked] [--deep]
    python code/lock_answers.py unlock  [--delete-archive]
    (all take --root <case folder> so the tests can work on a scratch copy; the default is the folder this script is in)

Why. A Claude Code subagent has Bash, Read and Glob, so it can open any file the user can. The material it must not see
is moved into one AES-256 encrypted zip and the plain files are gone until `unlock`.

What is locked
  core (the default)   data/key, design, data/requests, arms/build_notes.md, arms/tests, data/runs (the pilot logs)
  --extended           also world, arms/prompt_doc.md, arms/library, data/internal, data/facts.yaml, data/validation_report.json.
                       Recommended whenever S-arm runs use dev requests: world/request_history holds each dev request's accepted
                       query, and world/ holds the company documents that only D and L may have. Build the stage and packets first
                       (they are copies, in data/agent_runs/stage and packets); an arm reads its stage copy.
  --with-code          also code/ (the reference SQL sits in code/key_questions_*.py and the incident windows in code/config.py).
                       This script stays. The staged tools are self-contained, so runs do not need code/. Collecting and marking
                       do: unlock first.

The password. Read from the environment variable HAPAX_LOCK_PASSWORD, and if the process does not have it, from the Windows
user registry value of the same name (a shell opened before the variable was set does not see it). It is never printed, logged
or written to disk. `lock` refuses a missing password or one shorter than 12 characters. A password stored as a persistent user
variable is also visible to a subagent that runs `echo` or reads the registry: if that matters, set it for the one command only.

What `lock` does, in order, stopping at the first problem and changing nothing until the archive is proved good:
  1. check the password, that nothing is locked already, that every path to lock exists, that none is a link;
  2. refuse if a byte-identical copy of a locked file sits anywhere else in the case folder (the one allowed place for copies of
     arm material is data/agent_runs/stage, which holds the arm's own copies);
  3. write the archive (opaque entry names; the real paths are in an encrypted manifest), reopen it, decrypt every entry and
     compare its SHA-256 with the plain file;
  4. only then delete the plain files and the folders left empty, and run `status`. If a file cannot be deleted, the files already
     deleted are restored from the archive, the lock record is removed and the command fails: nothing is left half locked.
`status` proves the plain files are gone: no non-excluded file under any locked path, and no copy of any locked file's content
anywhere in the case folder (by SHA-256, from the hashes in the lock record, which carry no names). `--require-locked` makes
anything but "locked and clean" exit 1; `--deep` also decrypts the archive (needs the password) and checks every file.

`unlock` restores every file byte for byte (SHA-256 checked, modification times restored), refuses if a plain file is in the
way with different content, and keeps the archive renamed to ...restored-<time>.zip (nothing is deleted without --delete-archive).

Standard library plus pyzipper. Self-contained: it imports nothing from code/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import zipfile
from datetime import datetime
from pathlib import Path

PASSWORD_ENV = "HAPAX_LOCK_PASSWORD"
MIN_PASSWORD_LENGTH = 12
CORE_PATHS = ("data/key", "design", "data/requests", "arms/build_notes.md", "arms/tests", "data/runs")
EXTENDED_PATHS = ("world", "arms/prompt_doc.md", "arms/library", "data/internal", "data/facts.yaml", "data/validation_report.json")
CODE_PATH = "code"
OPTIONAL_PATHS = {"data/runs", "data/validation_report.json"}      # may be absent (nothing run yet) without stopping the lock
# Files that stay readable under a locked path: this script (and the bytecode Python may write for it).
STAY_PREFIXES = ("code/lock_answers", "code/__pycache__/lock_answers")
VAULT_RELATIVE = "data/agent_runs/vault"
ARCHIVE_NAME = "locked_answers.zip"
STATE_NAME = "lock_state.json"
STAGE_RELATIVE = "data/agent_runs/stage"
# Copies of these are expected inside the stage folder (the arms read them there); a copy of anything else is a leak.
STAGE_MAY_HOLD_COPIES_OF = ("arms/prompt_doc.md", "arms/library/", "world/", "code/hx_", "code/script_runner.py")
SCAN_SKIP_TOP = (VAULT_RELATIVE,)


class LockError(Exception):
    """A refusal or failure, reported in a sentence."""


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------

def read_user_registry_variable(name: str) -> "str | None":
    """The Windows user-level environment variable `name`, read from the registry (what
    [Environment]::GetEnvironmentVariable(name, 'User') returns). None off Windows or when it is not set."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _kind = winreg.QueryValueEx(key, name)
            return value if isinstance(value, str) else None
    except OSError:
        return None


def get_password() -> "str | None":
    """The lock password from the process environment, else from the user registry. Never printed or stored by this module."""
    value = os.environ.get(PASSWORD_ENV)
    if value:
        return value
    return read_user_registry_variable(PASSWORD_ENV) or None


def require_password(for_lock: bool, password: "str | None" = None) -> str:
    password = password if password is not None else get_password()
    if not password:
        raise LockError(f"No password: set {PASSWORD_ENV} in the environment or as a Windows user variable (it is never printed or stored).")
    if for_lock and len(password) < MIN_PASSWORD_LENGTH:
        raise LockError(f"The password in {PASSWORD_ENV} is shorter than {MIN_PASSWORD_LENGTH} characters; refusing to lock with it.")
    return password


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    return bool(is_junction and is_junction(path))


def stays_readable(relative: str) -> bool:
    return relative.startswith(STAY_PREFIXES)


def paths_for(groups: list) -> list:
    chosen = list(CORE_PATHS)
    if "extended" in groups:
        chosen += list(EXTENDED_PATHS)
    if "code" in groups:
        chosen.append(CODE_PATH)
    return chosen


def enumerate_locked(root: Path, rel_paths: list) -> tuple:
    """(files, directories, missing_required, problems). files: {relative posix path: absolute Path}. Excluded files are left out.
    Links are a problem (the lock would follow or lose them)."""
    files, directories, missing, problems = {}, [], [], []
    for relative in rel_paths:
        base = root / relative
        if not base.exists():
            if relative not in OPTIONAL_PATHS:
                missing.append(relative)
            continue
        if is_link(base):
            problems.append(f"{relative} is a link")
            continue
        if base.is_file():
            if not stays_readable(relative):
                files[relative] = base
            continue
        for current, subdirs, names in os.walk(base):
            current_path = Path(current)
            for name in list(subdirs):
                if is_link(current_path / name):
                    problems.append(f"{(current_path / name).relative_to(root).as_posix()} is a link")
                    subdirs.remove(name)
            directories.append(current_path.relative_to(root).as_posix())
            for name in names:
                path = current_path / name
                relative_file = path.relative_to(root).as_posix()
                if is_link(path):
                    problems.append(f"{relative_file} is a link")
                elif not stays_readable(relative_file):
                    files[relative_file] = path
    return files, sorted(set(directories)), missing, problems


def zone_ok(relative: str) -> bool:
    """True if copies of this file may sit in the stage folder (arm material and tools)."""
    return relative.startswith(STAGE_MAY_HOLD_COPIES_OF)


def find_copies(root: Path, index: dict, locked_files: set) -> list:
    """Files in the case folder (outside the locked set and the vault) whose content equals a locked file's.
    index: {size: {sha256: zone_ok}}. A copy inside the stage folder of a zone_ok file is allowed."""
    found = []
    stage_root = (root / STAGE_RELATIVE).resolve()
    for current, subdirs, names in os.walk(root):
        current_path = Path(current)
        relative_dir = current_path.relative_to(root).as_posix()
        if any(relative_dir == skip or relative_dir.startswith(skip + "/") for skip in SCAN_SKIP_TOP):
            subdirs[:] = []
            continue
        for name in names:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if relative in locked_files or is_link(path):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size == 0 or size not in index:
                continue
            digest = sha256_file(path)
            if digest in index[size]:
                in_stage = stage_root in path.resolve().parents
                if in_stage and index[size][digest]:
                    continue
                found.append(relative)
    return found


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

def open_archive(path: Path, mode: str, password: str):
    import pyzipper
    archive = pyzipper.AESZipFile(path, mode, compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) if mode == "w" \
        else pyzipper.AESZipFile(path, mode)
    archive.setpassword(password.encode("utf-8"))
    if mode == "w":
        archive.setencryption(pyzipper.WZ_AES, nbits=256)
    return archive


def read_manifest(archive) -> dict:
    try:
        return json.loads(archive.read("manifest.json").decode("utf-8"))
    except zip_errors() as error:
        raise LockError("Wrong password, or the archive is damaged.") from error


def zip_errors() -> tuple:
    """The exceptions a wrong password or a damaged archive can raise (pyzipper has its own BadZipFile class)."""
    try:
        import pyzipper
        return (RuntimeError, zipfile.BadZipFile, pyzipper.BadZipFile)
    except ImportError:
        return (RuntimeError, zipfile.BadZipFile)


def read_entry(archive, entry_id: str) -> bytes:
    """One decrypted entry; a wrong password or a damaged archive becomes a LockError, not a traceback."""
    try:
        return archive.read(entry_id)
    except zip_errors() as error:
        raise LockError("Wrong password, or the archive is damaged.") from error


def write_archive(destination: Path, files: dict, directories: list, password: str) -> dict:
    """Write the encrypted archive of `files` and return the manifest. Entry names are opaque; paths live in the manifest."""
    entries = []
    with open_archive(destination, "w", password) as archive:
        for number, (relative, path) in enumerate(sorted(files.items()), start=1):
            data = path.read_bytes()
            entry_name = f"f{number:06d}.bin"
            archive.writestr(entry_name, data)
            entries.append({"id": entry_name, "path": relative, "sha256": sha256_bytes(data), "bytes": len(data),
                            "mtime_ns": path.stat().st_mtime_ns})
        manifest = {"version": 1, "created": datetime.now().isoformat(timespec="seconds"), "entries": entries, "directories": directories}
        archive.writestr("manifest.json", json.dumps(manifest, indent=1).encode("utf-8"))
    return manifest


def verify_archive(archive_path: Path, password: str, expected: dict) -> None:
    """Reopen the archive and compare every entry's decrypted content with the SHA-256 recorded from the plain files."""
    with open_archive(archive_path, "r", password) as archive:
        manifest = read_manifest(archive)
        if manifest["entries"] != expected["entries"]:
            raise LockError("The archive's manifest does not match what was written.")
        for entry in manifest["entries"]:
            data = read_entry(archive, entry["id"])
            if sha256_bytes(data) != entry["sha256"] or len(data) != entry["bytes"]:
                raise LockError(f"The archive entry for {entry['path']} does not match the plain file.")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def vault_paths(root: Path) -> tuple:
    vault = root / VAULT_RELATIVE
    return vault, vault / ARCHIVE_NAME, vault / STATE_NAME


def read_state(state_path: Path) -> "dict | None":
    return json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else None


def write_json_atomic(path: Path, data: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(temporary, path)


def remove_file(path: Path) -> None:
    try:
        os.remove(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        os.remove(path)


def remove_empty_dirs(root: Path, directories: list) -> None:
    for relative in sorted(directories, key=lambda item: item.count("/"), reverse=True):
        path = root / relative
        try:
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        except OSError:
            pass


def restore_entries(root: Path, archive, manifest: dict, only_missing: bool = True) -> list:
    """Write every file in the manifest back (checked against its SHA-256, modification time restored). Returns the paths written."""
    for relative in manifest["directories"]:
        (root / relative).mkdir(parents=True, exist_ok=True)
    written = []
    for entry in manifest["entries"]:
        target = root / entry["path"]
        if target.exists():
            if sha256_file(target) == entry["sha256"]:
                continue
            raise LockError(f"{entry['path']} exists with different content; not overwriting it.")
        data = read_entry(archive, entry["id"])
        if sha256_bytes(data) != entry["sha256"]:
            raise LockError(f"The archive entry for {entry['path']} fails its checksum.")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".restoring")
        temporary.write_bytes(data)
        os.replace(temporary, target)
        os.utime(target, ns=(entry["mtime_ns"], entry["mtime_ns"]))
        written.append(entry["path"])
    return written


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def command_lock(root: Path, groups: list, password: "str | None" = None, say=print, delete_hook=None) -> dict:
    password = require_password(True, password)
    vault, archive_path, state_path = vault_paths(root)
    if state_path.exists() or archive_path.exists():
        raise LockError("A lock record or archive is already in the vault; run `status` (and `unlock` if it is locked) first.")
    rel_paths = paths_for(groups)
    files, directories, missing, problems = enumerate_locked(root, rel_paths)
    if missing:
        raise LockError("Cannot lock: these paths do not exist (already locked, or moved?): " + ", ".join(missing))
    if problems:
        raise LockError("Cannot lock: " + "; ".join(problems))
    if not files:
        raise LockError("Nothing to lock.")
    say(f"Locking {len(files)} files under {len(rel_paths)} paths ({', '.join(groups)}) ...")
    hashes = {relative: sha256_file(path) for relative, path in files.items()}
    index = {}
    for relative, path in files.items():
        size = path.stat().st_size
        if size:
            index.setdefault(size, {})[hashes[relative]] = zone_ok(relative)
    copies = find_copies(root, index, set(files))
    if copies:
        shown = ", ".join(copies[:6]) + (" ..." if len(copies) > 6 else "")
        raise LockError(f"Refusing to lock: {len(copies)} file(s) elsewhere are byte-identical copies of locked files and would stay readable: {shown}")
    vault.mkdir(parents=True, exist_ok=True)
    partial = vault / (ARCHIVE_NAME + ".partial")
    if partial.exists():
        remove_file(partial)
    manifest = write_archive(partial, files, directories, password)
    verify_archive(partial, password, manifest)
    os.replace(partial, archive_path)
    say(f"  archive written and checked: {archive_path.stat().st_size:,} bytes, {len(manifest['entries'])} files verified by SHA-256")
    state = {"version": 1, "status": "locking", "locked_at": datetime.now().isoformat(timespec="seconds"), "groups": groups, "roots": rel_paths,
             "file_count": len(files), "total_bytes": sum(entry["bytes"] for entry in manifest["entries"]),
             "archive_sha256": sha256_file(archive_path), "archive_bytes": archive_path.stat().st_size,
             "files": sorted([{"sha256": entry["sha256"], "bytes": entry["bytes"], "zone_ok": zone_ok(entry["path"])} for entry in manifest["entries"]],
                             key=lambda item: (item["sha256"], item["bytes"]))}
    write_json_atomic(state_path, state)
    failures = []
    for relative, path in sorted(files.items()):
        try:
            (delete_hook or remove_file)(path)
        except OSError as error:
            failures.append(f"{relative}: {error}")
    if failures:
        say(f"  could not delete {len(failures)} file(s); putting everything back.")
        with open_archive(archive_path, "r", password) as archive:
            restore_entries(root, archive, read_manifest(archive))
        state_path.unlink()
        aborted = vault / f"locked_answers.aborted-{datetime.now():%Y%m%d-%H%M%S}.zip"
        os.replace(archive_path, aborted)
        raise LockError("Lock aborted and undone, nothing is left half locked. Could not delete: " + "; ".join(failures[:4]))
    remove_empty_dirs(root, directories)
    state["status"] = "locked"
    write_json_atomic(state_path, state)
    report = status_report(root)
    if not report["clean"]:
        say("  the status check after locking found problems; putting everything back.")
        with open_archive(archive_path, "r", password) as archive:
            restore_entries(root, archive, read_manifest(archive))
        state_path.unlink()
        os.replace(archive_path, vault / f"locked_answers.aborted-{datetime.now():%Y%m%d-%H%M%S}.zip")
        raise LockError("Lock aborted and undone: " + "; ".join(report["problems"][:4]))
    say(f"LOCKED: {len(files)} files are in the archive and no plain file remains.")
    return state


def status_report(root: Path, password: "str | None" = None, deep: bool = False) -> dict:
    """The facts about the lock. clean=True means: locked, archive intact, no plain file under a locked path, no copy anywhere."""
    vault, archive_path, state_path = vault_paths(root)
    state = read_state(state_path)
    report = {"state": None, "clean": False, "problems": [], "lines": []}
    if state is None:
        missing = [relative for relative in CORE_PATHS if relative not in OPTIONAL_PATHS and not (root / relative).exists()]
        if archive_path.exists():
            report["state"] = "inconsistent"
            report["problems"].append("an archive is in the vault but there is no lock record")
        elif missing:
            report["state"] = "inconsistent"
            report["problems"].append("no lock record, but these locked-set paths are missing: " + ", ".join(missing))
        else:
            report["state"] = "unlocked"
            report["lines"].append("UNLOCKED: the held-out files are readable.")
        return report
    report["state"] = state["status"]
    if state["status"] != "locked":
        report["problems"].append(f"the lock record says '{state['status']}' (an interrupted lock); run `unlock` to restore")
        return report
    if not archive_path.is_file():
        report["problems"].append("the archive named by the lock record is missing")
        return report
    if sha256_file(archive_path) != state["archive_sha256"]:
        report["problems"].append("the archive's checksum differs from the lock record")
    remaining = []
    for relative in state["roots"]:
        base = root / relative
        if not base.exists():
            continue
        if base.is_file():
            if not stays_readable(relative):
                remaining.append(relative)
            continue
        for current, _subdirs, names in os.walk(base):
            for name in names:
                relative_file = (Path(current) / name).relative_to(root).as_posix()
                if not stays_readable(relative_file):
                    remaining.append(relative_file)
    if remaining:
        report["problems"].append(f"{len(remaining)} plain file(s) remain under locked paths, for example {remaining[0]}")
    index = {}
    for item in state["files"]:
        if item["bytes"]:
            index.setdefault(item["bytes"], {})[item["sha256"]] = item["zone_ok"]
    copies = find_copies(root, index, set())
    if copies:
        report["problems"].append(f"{len(copies)} file(s) are byte-identical copies of locked files, for example {copies[0]}")
    if deep:
        try:
            pw = require_password(False, password)
            with open_archive(archive_path, "r", pw) as archive:
                manifest = read_manifest(archive)
                for entry in manifest["entries"]:
                    if sha256_bytes(read_entry(archive, entry["id"])) != entry["sha256"]:
                        report["problems"].append(f"archive entry for {entry['path']} fails its checksum")
            report["lines"].append(f"deep check: all {len(manifest['entries'])} archive entries decrypt and match their checksums")
        except LockError as error:
            report["problems"].append(f"deep check failed: {error}")
    if not report["problems"]:
        report["clean"] = True
        report["lines"].insert(0, f"LOCKED: {state['file_count']} files in the archive since {state['locked_at']}; "
                                  "no plain file remains under the locked paths and no copy of any locked file's content was found in the case folder.")
    return report


def command_unlock(root: Path, password: "str | None" = None, delete_archive: bool = False, say=print) -> list:
    vault, archive_path, state_path = vault_paths(root)
    state = read_state(state_path)
    if state is None or not archive_path.is_file():
        raise LockError("Nothing to unlock: there is no lock record or no archive in the vault.")
    password = require_password(False, password)
    if sha256_file(archive_path) != state["archive_sha256"]:
        raise LockError("The archive's checksum differs from the lock record; not unlocking from it.")
    with open_archive(archive_path, "r", password) as archive:
        manifest = read_manifest(archive)
        conflicts = [entry["path"] for entry in manifest["entries"]
                     if (root / entry["path"]).exists() and sha256_file(root / entry["path"]) != entry["sha256"]]
        if conflicts:
            raise LockError("Plain files with different content are in the way, nothing restored: " + ", ".join(conflicts[:5]))
        written = restore_entries(root, archive, manifest)
        for entry in manifest["entries"]:
            if sha256_file(root / entry["path"]) != entry["sha256"]:
                raise LockError(f"{entry['path']} fails its checksum after restoring.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if delete_archive:
        remove_file(archive_path)
        state_path.unlink()
        say(f"UNLOCKED: {len(manifest['entries'])} files restored and checked; the archive was deleted (--delete-archive).")
    else:
        os.replace(archive_path, vault / f"locked_answers.restored-{stamp}.zip")
        os.replace(state_path, vault / f"lock_state.restored-{stamp}.json")
        say(f"UNLOCKED: {len(manifest['entries'])} files restored and checked ({len(written)} written); the archive is kept as locked_answers.restored-{stamp}.zip.")
    return written


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def main(argv: list = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Lock and unlock the held-out files for agent runs.")
    parser.add_argument("command", choices=["lock", "unlock", "status"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent, help="the case folder (default: this script's)")
    parser.add_argument("--extended", action="store_true", help="lock: also world/, arms/prompt_doc.md, arms/library, data/internal, data/facts.yaml")
    parser.add_argument("--with-code", action="store_true", help="lock: also code/ (this script stays)")
    parser.add_argument("--require-locked", action="store_true", help="status: exit 1 unless locked and clean")
    parser.add_argument("--deep", action="store_true", help="status: also decrypt the archive and check every file (needs the password)")
    parser.add_argument("--delete-archive", action="store_true", help="unlock: delete the archive after a checked restore")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "lock":
            groups = ["core"] + (["extended"] if args.extended else []) + (["code"] if args.with_code else [])
            command_lock(root, groups)
            return 0
        if args.command == "unlock":
            command_unlock(root, delete_archive=args.delete_archive)
            return 0
        report = status_report(root, deep=args.deep)
        for line in report["lines"]:
            print(line)
        for problem in report["problems"]:
            print("PROBLEM: " + problem)
        if report["state"] == "unlocked" and not args.require_locked:
            return 0
        return 0 if report["clean"] else 1
    except LockError as error:
        print(f"{args.command}: {error}")
        return 1
    except zip_errors():
        print(f"{args.command}: the archive is not a readable zip (damaged?).")
        return 1
    except ImportError:
        print("pyzipper is not installed in this Python (pip install pyzipper).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
