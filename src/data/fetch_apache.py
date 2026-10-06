"""Download monthly mbox archives of two Apache user-support mailing lists.

Run from the project root:
    python -m src.data.fetch_apache

Why these lists: users@tomcat.apache.org and users@kafka.apache.org are busy,
written by people rather than bots, and keep full headers (Received,
In-Reply-To, References, Authentication-Results). They give PretextGuard real
modern benign mail and real threads for N2's header signals. Chosen on
6 Oct 2026 from a one-month sample of four lists (spark and httpd had only
3 messages that month).

Each month is one request to the public archive at lists.apache.org, saved as
data/raw/apache/<list>/<YYYY-MM>.mbox. Months already on disk are skipped, so
the script is safe to rerun after a dropped connection.
"""

import time

import requests

from src.data.paths import APACHE_DIR, relative

API_URL = "https://lists.apache.org/api/mbox.lua"

# (folder name under data/raw/apache, list name, list domain)
LISTS = [
    ("tomcat_users", "users", "tomcat.apache.org"),
    ("kafka_users", "users", "kafka.apache.org"),
]

FIRST_MONTH = (2024, 10)  # October 2024
LAST_MONTH = (2026, 9)    # September 2026, so 24 complete months

PAUSE_SECONDS = 1          # wait between downloads, to be polite to the ASF's servers
MAX_BYTES = 50 * 1024**2   # refuse any single month larger than 50 MB
ATTEMPTS = 3               # tries per month before giving up on it

HEADERS = {"User-Agent": "PretextGuard student research project (github.com/Nagasai-Datta/PretextGuard)"}


def month_list(first, last):
    """Return every month from first to last inclusive as 'YYYY-MM' strings."""
    year, month = first
    months = []
    while (year, month) <= last:
        months.append(f"{year}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def count_messages(data):
    """Count the messages in mbox bytes: each one starts with a line beginning 'From '."""
    if not data:
        return 0
    return data.count(b"\nFrom ") + (1 if data.startswith(b"From ") else 0)


def download_month(session, list_name, domain, month):
    """Fetch one month's mbox and return its bytes. Raise ValueError if it is not an mbox."""
    params = {"list": list_name, "domain": domain, "d": month}
    chunks = []
    size = 0
    # stream=True reads the reply in pieces, so we can stop a reply that is too large
    with session.get(API_URL, params=params, headers=HEADERS, timeout=(10, 120), stream=True) as response:
        response.raise_for_status()  # turn 404, 500 and similar into an exception
        for chunk in response.iter_content(chunk_size=64 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError(f"reply larger than {MAX_BYTES // 1024**2} MB; refused")
            chunks.append(chunk)

    data = b"".join(chunks)
    # An empty reply is a month with no messages. Anything else must look like
    # an mbox; an HTML error page or a JSON error message is refused.
    if data and not data.startswith(b"From "):
        raise ValueError("reply is not an mbox file (it does not start with 'From ')")
    return data


def download_with_retries(session, list_name, domain, month):
    """Call download_month up to ATTEMPTS times, waiting longer after each network failure."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return download_month(session, list_name, domain, month)
        except requests.RequestException as error:
            if attempt == ATTEMPTS:
                raise
            wait = 2**attempt  # 2 s, then 4 s
            print(f"    attempt {attempt} failed ({error}); retrying in {wait} s")
            time.sleep(wait)


def save(data, target):
    """Write bytes to target through a .part file, then make it read-only."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    part.write_bytes(data)
    part.rename(target)  # the finished name appears only once the write is complete
    target.chmod(0o444)  # read-only for everyone, like the other downloads


def main():
    months = month_list(FIRST_MONTH, LAST_MONTH)
    failed = []

    # A Session reuses one connection for all requests (like a keep-alive agent in Node).
    with requests.Session() as session:
        for folder, list_name, domain in LISTS:
            print(f"{list_name}@{domain} -> {relative(APACHE_DIR / folder)}")
            total_messages = 0
            total_bytes = 0
            for month in months:
                target = APACHE_DIR / folder / f"{month}.mbox"
                if target.is_file():
                    data = target.read_bytes()
                    status = "skip"
                else:
                    try:
                        data = download_with_retries(session, list_name, domain, month)
                    except (requests.RequestException, ValueError) as error:
                        print(f"  {month}  FAILED  {error}")
                        failed.append(f"{folder} {month}")
                        continue
                    time.sleep(PAUSE_SECONDS)
                    if not data:
                        # Not saved: an empty reply could also be a server glitch,
                        # so the month is simply asked for again on the next run.
                        print(f"  {month}  empty, nothing saved")
                        continue
                    save(data, target)
                    status = "new "

                messages = count_messages(data)
                total_messages += messages
                total_bytes += len(data)
                print(f"  {month}  {status}  {messages:5,} messages  {len(data) / 1024:8,.0f} KB")
            print(f"  total: {len(months)} months, {total_messages:,} messages, {total_bytes / 1024**2:.1f} MB\n")

    if failed:
        print(f"{len(failed)} month(s) failed: {', '.join(failed)}. Run the script again to retry them.")
        raise SystemExit(1)
    print("All months downloaded.")


if __name__ == "__main__":
    main()
