"""Check every downloaded file in data/raw/ and unpack the archives safely.

Run from the project root:
    python -m src.data.unpack

What it does, in order:
1. Checks that every expected download is present and really is the type its
   name says, by reading its first bytes ("magic bytes"), not its extension.
2. Checks that every Nazario file is an mbox (starts with "From ").
3. Unpacks each archive into a folder next to it, named after the archive:
   data/raw/enron/enron_mail_20150507.tar.gz -> data/raw/enron/enron_mail_20150507/

Security: these files come from the internet and some hold live phishing.
- Tar archives are unpacked with Python's "data" filter, which refuses any
  member that would land outside the target folder (path traversal such as
  "../../.zshrc"), absolute paths, device files and links pointing outside.
- Zip members are checked for the same escape before anything is written.
- An archive that would unpack to more than MAX_UNPACKED_BYTES is refused,
  so a "decompression bomb" cannot fill the disk.
- Unpacked files are made read-only, like the downloads themselves.
- Nothing inside the archives is opened, run or parsed here.

Safe to rerun: archives already unpacked are skipped, and an unpack that was
interrupted (for example with Ctrl+C) is deleted and started again.
"""

import shutil
import tarfile
import zipfile

from tqdm import tqdm

from src.data.paths import (
    ENRON_DIR,
    KAGGLE_DIR,
    NAZARIO_DIR,
    PHISHING_POT_DIR,
    SPAMASSASSIN_DIR,
    relative,
)

# Every file format starts with a fixed signature. We compare the first bytes
# of each download with the signature its type must have.
MAGIC = {
    "bz2": b"BZh",
    "gzip": b"\x1f\x8b",
    "zip": b"PK\x03\x04",
    "mbox": b"From ",
}

# Every archive we expect, with the type its first bytes must show.
# Enron is last because it is by far the slowest to unpack.
ARCHIVES = [
    (SPAMASSASSIN_DIR / "20030228_easy_ham.tar.bz2", "bz2"),
    (SPAMASSASSIN_DIR / "20030228_easy_ham_2.tar.bz2", "bz2"),
    (SPAMASSASSIN_DIR / "20030228_hard_ham.tar.bz2", "bz2"),
    (SPAMASSASSIN_DIR / "20030228_spam.tar.bz2", "bz2"),
    (SPAMASSASSIN_DIR / "20050311_spam_2.tar.bz2", "bz2"),
    (KAGGLE_DIR / "phish_no_more.zip", "zip"),
    (PHISHING_POT_DIR / "phishing_pot-main.zip", "zip"),
    (ENRON_DIR / "enron_mail_20150507.tar.gz", "gzip"),
]

ARCHIVE_SUFFIXES = (".tar.bz2", ".tar.gz", ".zip")

# Refuse any archive whose contents add up to more than 5 GB.
MAX_UNPACKED_BYTES = 5 * 1024**3


def human_size(num_bytes):
    """Format a byte count for printing, for example 443254787 -> '422.7 MB'."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def has_magic(path, kind):
    """Return True if the file starts with the signature bytes of type `kind`."""
    signature = MAGIC[kind]
    with open(path, "rb") as f:
        return f.read(len(signature)) == signature


def check_file(path, kind):
    """Print one line about a download and return 1 if it is missing or the wrong type, else 0."""
    if not path.is_file():
        print(f"  MISSING     {relative(path)}")
        return 1
    if not has_magic(path, kind):
        print(f"  WRONG TYPE  {relative(path)} (expected {kind})")
        return 1
    print(f"  ok  {kind:<4} {human_size(path.stat().st_size):>10}  {relative(path)}")
    return 0


def check_downloads():
    """Check every expected archive and every Nazario file. Return the number of problems."""
    print("Checking downloads")
    problems = 0
    for path, kind in ARCHIVES:
        problems += check_file(path, kind)

    # Nazario files are not archives: each one is a single mbox file.
    # Names starting with "." (such as macOS's .DS_Store) are skipped.
    nazario_files = []
    if NAZARIO_DIR.is_dir():
        nazario_files = sorted(
            p for p in NAZARIO_DIR.iterdir() if p.is_file() and not p.name.startswith(".")
        )
    if not nazario_files:
        print(f"  MISSING     no files in {relative(NAZARIO_DIR)}")
        problems += 1
    for path in nazario_files:
        problems += check_file(path, "mbox")
    return problems


def archive_stem(path):
    """Archive name without its extension: 'enron_mail_20150507.tar.gz' -> 'enron_mail_20150507'."""
    for suffix in ARCHIVE_SUFFIXES:
        if path.name.endswith(suffix):
            return path.name[: -len(suffix)]
    raise ValueError(f"Not a known archive type: {path.name}")


def limited_tar_members(tar, tally):
    """Hand tar members to the extractor one at a time, keeping a running tally.

    `tally` is a dict this function updates as it goes: "bytes" (total size so
    far) and "files" (regular files so far). Raises ValueError as soon as the
    total passes MAX_UNPACKED_BYTES, which stops the unpack.
    """
    for member in tar:
        tally["bytes"] += member.size
        if tally["bytes"] > MAX_UNPACKED_BYTES:
            raise ValueError(f"would unpack to more than {human_size(MAX_UNPACKED_BYTES)}; refused")
        if member.isfile():
            tally["files"] += 1
        yield member


def extract_tar(archive, dest):
    """Unpack a .tar.bz2 or .tar.gz into dest. Return the number of files the archive holds."""
    tally = {"bytes": 0, "files": 0}
    with tarfile.open(archive, mode="r:*") as tar:  # "r:*" detects bz2 or gzip itself
        members = tqdm(limited_tar_members(tar, tally), desc=f"  {archive.name}", unit=" entries")
        tar.extractall(path=dest, members=members, filter="data")
    return tally["files"]


def extract_zip(archive, dest):
    """Unpack a .zip into dest after checking every member. Return the number of files it holds."""
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        members = zf.infolist()

        total = sum(m.file_size for m in members)
        if total > MAX_UNPACKED_BYTES:
            raise ValueError(f"would unpack to {human_size(total)}; refused")

        # Check every name before writing anything: each must stay inside dest.
        for m in members:
            target = (dest_resolved / m.filename).resolve()
            if not target.is_relative_to(dest_resolved):
                raise ValueError(f"member {m.filename!r} would land outside the target folder; refused")

        for m in tqdm(members, desc=f"  {archive.name}", unit=" entries"):
            zf.extract(m, dest)
    return sum(1 for m in members if not m.is_dir())


def make_read_only(folder):
    """Remove write permission from every file under folder. Return how many files there are."""
    count = 0
    for path in folder.rglob("*"):
        if path.is_file() and not path.is_symlink():
            path.chmod(path.stat().st_mode & ~0o222)  # 0o222 = the three "write" bits
            count += 1
    return count


def unpack(archive):
    """Unpack one archive into a folder named after it, unless that was already done."""
    final_dir = archive.parent / archive_stem(archive)
    if final_dir.is_dir():
        print(f"  skip  {relative(final_dir)} (already unpacked)")
        return

    # Unpack into a temporary folder first and rename it only when finished,
    # so a half-unpacked folder is never mistaken for a complete one.
    temp_dir = archive.parent / f"_unpacking_{archive_stem(archive)}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)  # left over from an interrupted run
    temp_dir.mkdir()

    try:
        if archive.name.endswith(".zip"):
            expected = extract_zip(archive, temp_dir)
        else:
            expected = extract_tar(archive, temp_dir)
    except Exception as error:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise SystemExit(f"  STOPPED  {archive.name}: {error}") from error

    on_disk = make_read_only(temp_dir)
    temp_dir.rename(final_dir)
    print(f"  done  {relative(final_dir)}  ({on_disk:,} files)")

    # macOS disks treat "Inbox" and "inbox" as the same name, so two archive
    # members that differ only in case would overwrite each other. Catch it.
    if on_disk != expected:
        print(f"  WARNING  the archive holds {expected:,} files but {on_disk:,} are on disk")


def main():
    problems = check_downloads()
    if problems:
        print(f"\n{problems} problem(s) found. Nothing was unpacked; fix them and run again.")
        raise SystemExit(1)

    print("\nUnpacking archives")
    for archive, _kind in ARCHIVES:
        unpack(archive)
    print("\nAll downloads checked and unpacked.")


if __name__ == "__main__":
    main()
