"""Copy to and paste from the macOS clipboard, so a batch goes to the chat and a reply comes back without a text editor.

copy(text) and paste() call the macOS tools pbcopy and pbpaste directly (no shell, nothing is
interpreted). On a machine without them (Linux, a server) they raise ClipboardError and the caller
prints the file path to open by hand.
"""

import os
import shutil
import subprocess

MAX_PASTE_BYTES = 2_000_000  # a chat reply is a few thousand characters; refuse anything absurd

# pbcopy and pbpaste read the locale to pick an encoding; UTF-8 keeps curly quotes and accents intact.
_ENV = {**os.environ, "LC_CTYPE": "UTF-8"}


class ClipboardError(RuntimeError):
    pass


def copy(text):
    if not shutil.which("pbcopy"):
        raise ClipboardError("pbcopy not found (this helper needs macOS)")
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, env=_ENV)


def paste():
    if not shutil.which("pbpaste"):
        raise ClipboardError("pbpaste not found (this helper needs macOS)")
    result = subprocess.run(["pbpaste"], capture_output=True, check=True, env=_ENV)
    if len(result.stdout) > MAX_PASTE_BYTES:
        raise ClipboardError("the clipboard holds far more text than any chat reply")
    return result.stdout.decode("utf-8", errors="replace")
