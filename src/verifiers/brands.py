"""The real registered domains of the often-imitated organisations. Data only; header_verifier.py reads it.

KNOWN_ORGS in src/claims/patterns.py lists the organisations the claim extractor recognises by name. This file
attaches to each one the domains that organisation really sends mail from, so the header verifier can ask: the
email says "PayPal Security Team", does the sender belong to PayPal?

RULES FOR THIS FILE
- Only domains that are certain are written here (the organisation's own primary domains and its documented
  notification domains). Nothing is guessed. A domain that is missing makes the verifier more suspicious of a
  genuine message (a "medium" contradiction, never "high"), so a gap costs a little precision and never opens a hole.
- No domain here may be a free mailbox domain (outlook.com, yahoo.com, icloud.com ...): anyone can get an address
  there, so a message from it proves nothing about the organisation. Organisations whose only domains are such
  mailbox domains are listed in NO_DOMAINS_YET, with the reason, instead of being given a wrong entry.
- Names are the spellings of KNOWN_ORGS; an alias maps another spelling to the same organisation.
- Third-party mailers (amazonses.com, sendgrid.net ...) are not brand domains. Mail a brand sends through one is
  recognised only when the brand's own domain authenticates it (see header_verifier.py).
- CONFIRM lists the entries to double-check by hand; the command is in src/verifiers/README.md. They are all
  believed correct, but they are the least common, so a typing mistake there would matter most.

Every claim of "this domain belongs to this organisation" is checked by src/verifiers/build.py against the freemail
list (none may overlap) and against KNOWN_ORGS (every name must be here or in NO_DOMAINS_YET).
"""

BRAND_DOMAINS = {
    "PayPal": ("paypal.com",),
    "eBay": ("ebay.com", "ebay.co.uk", "ebay.de", "ebay.fr", "ebay.it", "ebay.es", "ebay.ca", "ebay.com.au"),
    "Amazon": ("amazon.com", "amazon.co.uk", "amazon.de", "amazon.fr", "amazon.it", "amazon.es", "amazon.ca",
               "amazon.com.au", "amazon.in", "amazon.co.jp"),
    "Apple": ("apple.com",),
    "Microsoft": ("microsoft.com", "microsoftonline.com", "office.com"),
    "Google": ("google.com",),
    "Facebook": ("facebook.com", "facebookmail.com", "fb.com", "meta.com"),
    "Netflix": ("netflix.com",),
    "DocuSign": ("docusign.com", "docusign.net"),
    "Dropbox": ("dropbox.com",),
    "LinkedIn": ("linkedin.com",),
    "WhatsApp": ("whatsapp.com",),
    "Instagram": ("instagram.com", "facebookmail.com"),
    "Adobe": ("adobe.com",),
    "Zoom": ("zoom.us", "zoom.com"),
    "DHL": ("dhl.com", "dhl.de"),
    "FedEx": ("fedex.com",),
    "UPS": ("ups.com",),
    "USPS": ("usps.com",),
    "IRS": ("irs.gov",),
    "Chase": ("chase.com", "jpmorgan.com", "jpmorganchase.com"),
    "Wells Fargo": ("wellsfargo.com",),
    "Bank of America": ("bankofamerica.com",),
    "Citibank": ("citibank.com", "citi.com"),
    "HSBC": ("hsbc.com", "hsbc.co.uk"),
    "Barclays": ("barclays.com", "barclays.co.uk"),
    "Santander": ("santander.com", "santander.co.uk"),
    "Lloyds": ("lloydsbank.com", "lloydsbank.co.uk", "lloydsbankinggroup.com"),
    "NatWest": ("natwest.com",),
    "Western Union": ("westernunion.com",),
    "GoDaddy": ("godaddy.com",),
    "Visa": ("visa.com",),
    "Mastercard": ("mastercard.com",),
    "American Express": ("americanexpress.com",),
    "Capital One": ("capitalone.com",),
    "USAA": ("usaa.com",),
    "SunTrust": ("suntrust.com", "truist.com"),
    "Regions": ("regions.com",),
    "Skrill": ("skrill.com", "moneybookers.com"),
    "Alibaba": ("alibaba.com",),
    "Trust Wallet": ("trustwallet.com",),
    "Coinbase": ("coinbase.com",),
    "Binance": ("binance.com",),
    "Steam": ("steampowered.com", "steamcommunity.com"),
    "Spotify": ("spotify.com",),
    "Walmart": ("walmart.com",),
    "Target": ("target.com",),
    "Costco": ("costco.com",),
    "AT&T": ("att.com",),
    "Verizon": ("verizon.com", "verizonwireless.com"),
    "Comcast": ("comcast.com", "xfinity.com"),
}

# Another spelling of an organisation in KNOWN_ORGS, mapped to the key of BRAND_DOMAINS.
ALIASES = {
    "Outlook": "Microsoft",
    "Office 365": "Microsoft",
    "Moneybookers": "Skrill",
}

# Known organisations with no domain written yet, and why. A claim naming one of them can still be checked for a
# free-mailbox sender, but never against a domain list.
NO_DOMAINS_YET = {
    "Yahoo": "its mail comes from yahoo.com, a free mailbox domain, so a domain list would prove nothing; its corporate domain is not confirmed",
}

# Entries to double-check by hand before the report (command in src/verifiers/README.md): domains that are not the
# organisation's main domain.
CONFIRM = (
    "facebookmail.com", "fb.com", "meta.com", "docusign.net", "zoom.com", "dhl.de", "jpmorganchase.com", "lloydsbankinggroup.com",
    "truist.com", "verizonwireless.com", "xfinity.com", "steamcommunity.com", "microsoftonline.com", "office.com", "moneybookers.com",
)

# Domains that look like they could be added, but are not certain: NOT used by the verifier.
NOT_CONFIRMED = ("dropboxmail.com", "paypal-communication.com", "usps.gov", "aexp.com", "yahooinc.com", "itunes.com")
