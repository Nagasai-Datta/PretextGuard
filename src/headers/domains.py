"""Domain helpers: registered domain, freemail list, lookalike score.

registered_domain("mail.paypal.com")        -> "paypal.com"
registered_domain("paypal.com.evil-site.ru") -> "evil-site.ru"   (what phishers count on)
registered_domain("paypal-billing.onmicrosoft.com") -> "paypal-billing.onmicrosoft.com" (a tenant)
is_freemail("gmail.com")                     -> True
lookalike_score("paypa1.com", "paypal.com")  -> 100.0 (look-alike characters mapped first)

Security: tldextract uses its built-in copy of the public suffix list and never
downloads anything; punycode (xn--...) is decoded and common look-alike
characters are mapped before comparing, so homograph domains such as
"pаypal.com" (Cyrillic "а") score as look-alikes.
"""

from functools import lru_cache

import tldextract
from rapidfuzz import fuzz

# suffix_list_urls=() means: never download the list, use the copy shipped inside tldextract.
_extract = tldextract.TLDExtract(suffix_list_urls=())

# Free and consumer mailbox providers, written by hand: anyone can get an address
# there, so the domain says nothing about which organisation the sender belongs to.
# build.py prints the most common sender domains per source, so a big provider
# missing from this list shows up and can be added.
FREEMAIL = frozenset({
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.co.uk", "yahoo.co.in", "yahoo.fr", "yahoo.de", "yahoo.es", "yahoo.it",
    "yahoo.ca", "yahoo.com.au", "yahoo.com.br", "ymail.com", "rocketmail.com",
    "hotmail.com", "hotmail.co.uk", "hotmail.fr", "hotmail.de", "hotmail.it", "outlook.com",
    "live.com", "live.co.uk", "msn.com",
    "aol.com", "aim.com",
    "icloud.com", "me.com", "mac.com",
    "protonmail.com", "proton.me", "pm.me",
    "gmx.com", "gmx.net", "gmx.de", "web.de", "mail.com", "email.com",
    "yandex.com", "yandex.ru", "mail.ru", "inbox.ru", "list.ru", "bk.ru", "rambler.ru",
    "zoho.com", "tutanota.com", "fastmail.com", "hushmail.com", "lycos.com", "excite.com",
    "qq.com", "163.com", "126.com", "sina.com", "yeah.net",
    "rediffmail.com", "naver.com", "hanmail.net", "libero.it", "orange.fr", "laposte.net",
    "t-online.de", "comcast.net", "verizon.net", "att.net", "sbcglobal.net", "earthlink.net",
    # added in Phase 3 step 2, from the sender domains build.py printed and other large providers
    "virgilio.it", "tiscali.it", "tiscali.co.uk", "netscape.net", "latinmail.com", "maktoob.com",
    "juno.com", "netzero.net", "usa.net", "hotmail.es", "live.fr", "aol.co.uk", "yahoo.co.jp",
    "gmx.at", "gmx.ch", "freenet.de", "seznam.cz", "wp.pl", "o2.pl", "interia.pl", "abv.bg", "ukr.net",
    "sohu.com", "foxmail.com", "aliyun.com", "uol.com.br", "bol.com.br", "terra.com.br", "sapo.pt",
    "btinternet.com", "cox.net", "charter.net", "shaw.ca", "rogers.com", "sympatico.ca", "bigpond.com",
})

# Shared platforms where anyone can create a sub-domain for free: every Microsoft 365
# tenant gets <name>.onmicrosoft.com, every Firebase project <name>.firebaseapp.com.
# The <name> part is chosen by whoever signed up, so it is treated as the registered
# name (it is what a look-alike tenant such as "acme-payroll" imitates). Both are
# common senders in phishing_pot.
OPEN_PLATFORMS = frozenset({"onmicrosoft.com", "firebaseapp.com"})

# Characters that look alike, mapped to the letter they imitate before comparing.
# Two-letter tricks first ("rn" looks like "m", "vv" like "w"), then single characters.
CONFUSABLE_PAIRS = [("rn", "m"), ("vv", "w")]
CONFUSABLE_CHARS = str.maketrans({
    "0": "o", "1": "l", "3": "e", "5": "s", "|": "l",
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s",
})


@lru_cache(maxsize=200_000)
def split_domain(domain):
    """(name, suffix) of a domain's registered part: 'mail.paypal.co.uk' -> ('paypal', 'co.uk').

    On an open platform the tenant is the name: 'acme.onmicrosoft.com' -> ('acme', 'onmicrosoft.com').
    """
    if not isinstance(domain, str) or not domain:  # None, or pandas' NaN for a missing value
        return None, None
    parts = _extract(domain.lower().strip("."))
    if not (parts.domain and parts.suffix):
        return None, None
    platform = f"{parts.domain}.{parts.suffix}"
    if platform in OPEN_PLATFORMS and parts.subdomain:
        return parts.subdomain.rsplit(".", 1)[-1], platform
    return parts.domain, parts.suffix


def registered_domain(domain):
    """The part of a domain that someone actually registered, or None."""
    name, suffix = split_domain(domain)
    return f"{name}.{suffix}" if name else None


def is_freemail(domain):
    """True if anyone can get an address on this domain: a free mailbox provider or an open platform."""
    name, suffix = split_domain(domain)
    if not name:
        return False
    return f"{name}.{suffix}" in FREEMAIL or suffix in OPEN_PLATFORMS


def skeleton(name):
    """The name with punycode decoded and look-alike characters mapped: 'paypa1' -> 'paypal'."""
    if name.startswith("xn--"):
        try:
            name = name.encode("ascii").decode("idna")
        except UnicodeError:
            pass
    name = name.lower()
    for pair, letter in CONFUSABLE_PAIRS:
        name = name.replace(pair, letter)
    return name.translate(CONFUSABLE_CHARS)


def lookalike_score(domain_a, domain_b):
    """How alike two domains look, 0 to 100, comparing only their registered names; None if either is missing."""
    name_a, _ = split_domain(domain_a)
    name_b, _ = split_domain(domain_b)
    if not (name_a and name_b):
        return None
    return round(fuzz.ratio(skeleton(name_a), skeleton(name_b)), 1)
