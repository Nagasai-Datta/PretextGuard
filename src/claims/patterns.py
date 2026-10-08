"""The claim patterns of Phase 7, as data only. extractor.py turns them into spaCy token patterns.

A claim is something the email asserts that a verifier can check ("this is David from Finance",
"reply to my private email", "update your bank details"). The eleven claim types are the ones of
src/data/label_schema.py (CLAIM_TYPES). Patterns are written from the claim definitions, general knowledge
of how business email compromise, phishing and advance-fee fraud are worded, and the TRAIN split only
(its labelled spans and the synthetic train emails). Nothing here was written from validation or test emails.
Each revision changes PATTERN_VERSION, which build.py saves in results/claim_checks.csv.

THE PATTERN LANGUAGE. A phrase is words separated by spaces; every word is one token of the email:

    verify        the token "verify" (upper or lower case)
    verif*        any token that starts with "verif" (verify, verified, verification ...)
    sign|log      either word; each alternative can end in * too:  verif*|confirm*|update
    !writing|to   any token EXCEPT these (use it to stop a pattern from matching the wrong sentence)
    =IT|HR        the token with exactly this capitalisation ("IT" the department, never "it" the pronoun)
    #             one token made of digits (a house number, a postcode)
    ?the          the token is optional
    ..3           up to 3 tokens of anything (between 1 and 6; never first or last)
    @PERSON       a run of tokens that spaCy marks as a PERSON (or @ORG for an organisation)

A pattern must start and end with a real word. The same tokenisation spaCy applies to the email is applied
to the phrase, so "don't" is two tokens (do, n't), "e-mail" is three (e, -, mail) and "[EMAIL]" is three
([, EMAIL, ]). Matching works on tokens, never on raw text with a regular expression, so its cost grows
in proportion to the length of the text (ReDoS-safe, as in Phases 2 to 4).

Each entry is (pattern id, phrase, strength). A strong phrase (confidence 0.9) is hard to say innocently, a
weak phrase (confidence 0.6) also appears in ordinary mail and is kept as a lower-confidence claim. Rules
that need entities or surface shapes (organisation names, signature blocks, phone numbers) live in
extractor.py and use the word lists below.
"""

PATTERN_VERSION = "0.4"

STRONG = 0.9
WEAK = 0.6

PHRASES = {
    "credential_request": [
        ("cr_verify_your", "verif*|confirm*|validat*|updat*|reactivat*|restor*|unlock*|renew* ..2 your ..2 account*|password*|mailbox|login|credential*|identity|profile|wallet|access|email", STRONG),
        ("cr_verify_info", "verif*|confirm*|validat* ..2 your ..2 information*|details|identity|data", STRONG),
        ("cr_click_to", "click|follow|visit|press ..4 to verif*|confirm*|updat*|validat*|sign|log|login|restor*|reactivat*|unlock*|access|renew*|activat*|reset*|secure", STRONG),
        ("cr_sign_in_to", "sign|log|login|logon ?in|on|into ?to your ..2 account*|mailbox|portal|online|profile|email|page|banking|wallet|paypal|ebay|amazon|apple|microsoft|google|facebook|bank", STRONG),
        ("cr_enter_your", "enter|provide|send|share|submit|supply|type|reply|respond|give|confirm|verify ..4 your ..2 password*|pin|passcode|username|credential*|login|otp|code", STRONG),
        ("cr_code", "enter|provide|send|share|read ..3 verification|security|authentication|confirmation code|otp|passcode|pin", STRONG),
        ("cr_verify_now", "verif*|confirm*|validat* ..1 now|today|immediately", WEAK),
        ("cr_secure_form", "complet*|fill ..3 secure|online ..2 form|page|portal", WEAK),
        ("cr_your_password", "your ..1 password*|passcode|credentials", WEAK),
        ("cr_sign_in", "sign|log in|on", WEAK),
    ],
    "reply_direction": [
        ("rd_private_address", "reply|respond|write|answer|send|email|contact|reach|call|text ..5 private|personal|alternative|alternate|direct|separate|secure|own|new|secret ..2 email|address|number|phone|telephone|mobile|line|inbox", STRONG),
        ("rd_directly", "reply|respond|write|answer ..3 directly|privately|personally|only|strictly", STRONG),
        ("rd_contact_me", "contact*|reach*|email*|messag*|text*|whatsapp|call|calling ..1 me ..1 directly|privately|personally|only|strictly|through|via|on|at|by", STRONG),
        ("rd_send_to_address", "send|reply|respond|write|forward ..4 to|via|through ..3 private|personal|alternative|alternate|new|following|below|my ..2 address|email|mail", STRONG),
        ("rd_my_mobile", "reply|text|call|contact|reach|send|message|respond ..5 my ..1 personal|private|direct|mobile|cell|own|text ..1 mobile|cell|phone|line|number|text|whatsapp", STRONG),
        ("rd_my_address", "my private|personal|alternative|alternate|new|other ..2 email|mail|address", WEAK),
        ("rd_messaging", "text|message|whatsapp|call|chat ..1 me ..2 on|at|via ..2 whatsapp|telegram|signal|viber|skype|number|phone|mobile|cell", STRONG),
        ("rd_address_below", "send|reply|respond|write|mail ..4 to ..4 address|email|mail below|given|provided|following", STRONG),
        ("rd_contact_by", "contact* ..2 us|agents|team|office|department|support|sender ..1 by|via|through|at ..1 email|telephone|phone|mail|mobile", WEAK),
        ("rd_get_back", "get ..1 back ..1 to me", WEAK),
        ("rd_contact_me_weak", "contact|reach|call|email me", WEAK),
    ],
    "data_request": [
        ("dr_send_sensitive", "send|provide|submit|forward|furnish|supply|reply|share|give|attach|upload|fill|complete ..3 your ..2 full|complete|personal|private|bank*|residential|home|mailing|tax|payroll|passport|identity|ssn|social|telephone|phone|fax|name*|age|occupation|nationality|particulars", STRONG),
        ("dr_card", "send|provide|enter|submit|verify|confirm|update|supply|give|reply|share ..3 your ..1 credit|debit ..1 card*|number*|details|information", STRONG),
        ("dr_staff_records", "staff|employee*|payroll|tax|student ..2 list*|records|forms|documents|files|data|information|statements|returns|w2|filings|particulars", STRONG),
        ("dr_fill_form", "complete|fill ..5 form|data|information|details", WEAK),
        ("dr_send_documents", "send|provide|share|submit|forward|furnish ..4 documents|documentation|records|files|logs|list|data|reports|statements|forms", WEAK),
        ("dr_additional", "additional|following|below|required|requested|necessary ..1 details|information|documents|data|particulars", WEAK),
        ("dr_bank_details", "bank|account|banking ..2 details|particulars|number|information", WEAK),
    ],
    "payment_request": [
        ("pr_pay_the", "pay|process|wire|remit|settle|authorize|authorise|approve|issue|release|initiate|proceed|finalize|finalise|arrange|schedule ..4 payment*|invoice*|wire|amount|balance|bill|fee*|payroll|reimbursement*|remittance*|refund*", STRONG),
        ("pr_make_payment", "make ..1 payment*", STRONG),
        ("pr_send_money", "pay|send|wire|transfer|remit ..3 money|funds|cash|deposit", WEAK),
        ("pr_wire_transfer", "wire|bank transfer*", STRONG),
        ("pr_overdue", "payment*|invoice*|balance|bill|fee*|amount ..3 due|overdue|outstanding|owed|unpaid", STRONG),
        ("pr_pending", "payment*|invoice*|balance|bill|fee*|amount ..3 pending|required", WEAK),
        ("pr_charged", "charged|debited ..3 to|from ..2 card|account", STRONG),
        ("pr_outstanding", "outstanding|unpaid|overdue ..1 invoice*|balance|payment*|bill|fee*", STRONG),
        ("pr_pay_now", "pay ..1 now|today|immediately|promptly", WEAK),
    ],
    "payment_change": [
        ("pc_change_details", "chang*|updat*|new|switch*|modif*|revis*|replac*|shift* ..3 bank*|banking|payment|payroll|billing|beneficiary|wire|deposit ..2 detail*|information|number|instruction*|account|particulars|method*", STRONG),
        ("pc_details_changed", "bank*|banking|billing|payment|payroll|beneficiary|account ..2 detail*|information|particulars ..3 chang*|updat*|new|replac*", WEAK),
        ("pc_direct_deposit", "direct deposit", WEAK),
    ],
    "gift_card": [
        ("gc_gift_card", "gift ..1 card*", STRONG),
        ("gc_gift_voucher", "gift ..1 certificate*|voucher*", WEAK),
        ("gc_buy_cards", "buy|purchase|get|obtain|pick|scratch|photograph ..3 the|these|those|some|several|few|five|ten|two|three|four|six|seven|eight|nine ..1 card*", WEAK),
    ],
    "prior_relationship": [
        ("pre_as_discussed", "as|per ?we|i|you ?previously|already|earlier|also discussed|agreed|mentioned|promised|talked|spoke|spoken|chatted|requested", STRONG),
        ("pre_following_our", "follow* ..1 up ..1 on|with|from ..1 our|my|the|your ..2 call|conversation|meeting|discussion|email|chat|message|talk|visit|session|walkthrough|exchange", STRONG),
        ("pre_following", "following ..1 our|my|your|the ..2 call|conversation|meeting|discussion|email|chat|talk|visit|exchange", STRONG),
        ("pre_our_last", "our|my ..1 last|previous|earlier|recent|prior|past ..1 call|conversation|meeting|discussion|email|chat|talk|visit|exchange|correspondence|session", STRONG),
        ("pre_in_response", "response|reply ..1 to ..1 our|my|your ..1 previous|earlier|last|recent ..1 email*|message*|mail|letter", STRONG),
        ("pre_great_seeing", "great|nice|good|lovely|wonderful ..1 seeing|meeting|speaking|catching|working|connecting|talking|chatting ..2 you|earlier|today|yesterday|last", STRONG),
        ("pre_speaking_with", "speaking|talking|chatting|meeting|catching|working ..1 with|up ..1 you", STRONG),
        ("pre_we_spoke", "we ..1 met|spoke|talked|discussed ..2 you|with|earlier|yesterday|last|before|at|on", STRONG),
        ("pre_got_your", "got|received|get ..1 your ..2 message*|email*|mail|call|letter|note|inquiry|enquiry|request", WEAK),
        ("pre_thanks_for", "thank* ..2 for ..1 your ..2 response|reply|email|message", WEAK),
        ("pre_met_you", "meeting|met|seeing|saw|catching|caught ..1 you|up ..2 at|on|last|during|with|earlier|yesterday", STRONG),
        ("pre_lunch_with", "lunch|dinner|coffee|drinks|breakfast ..1 with ..1 you", STRONG),
        ("pre_worked_together", "worked|working|worked ..1 together|with ..1 you", STRONG),
    ],
    "authority": [
        ("au_i_am_title", "i am|'m|are !writing|writting|contacting|sending|emailing|replying|reaching|forwarding|interested|happy|pleased|glad|sorry|not|so|very|just ..5 ceo|cfo|coo|cto|president|chairman|chairwoman|director|manager|officer|auditor|accountant|attorney|barrister|lawyer|secretary|minister|governor|commissioner|supervisor|administrator|controller|treasurer|executive|chief|head|assistant|aide|counsel|partner|dean|principal|founder|owner|superintendent|provost|chancellor|solicitor|judge|mayor|ambassador|senator|chair|official|advisor|adviser|spokesman|spokesperson", STRONG),
        ("au_as_the", "as ?the|your|a|an ..2 ceo|cfo|coo|cto|president|chairman|chairwoman|director|manager|officer|auditor|accountant|attorney|secretary|minister|governor|commissioner|supervisor|administrator|controller|treasurer|executive|chief|head", STRONG),
        ("au_this_is_the", "this is|'s ?the|your ..2 ceo|cfo|coo|cto|president|chairman|director|manager|officer|auditor|accountant|attorney|secretary|minister|governor|supervisor|administrator|controller|treasurer|executive|chief|head", STRONG),
        ("au_qualified_title", "senior|chief|general|executive|managing|deputy|assistant|former|internal|external|personal|top ..1 director|manager|officer|auditor|accountant|attorney|secretary|minister|governor|supervisor|administrator|controller|treasurer|president|chairman|counsel|partner", WEAK),
        ("au_sysadmin", "system|network|database|server|domain administrator*", WEAK),
        ("au_personal_to", "personal|private ..1 attorney|assistant|secretary|aide|accountant|lawyer|auditor|banker ..1 to", STRONG),
        ("au_title_of", "ceo|cfo|coo|cto|president|chairman|director|manager|officer|auditor|accountant|governor|supervisor|administrator|controller|treasurer|executive|chief|head of ?the ..2 operations|compliance|finance|audit*|human|hr|accounts|payroll|it|security|procurement|legal|marketing|sales|treasury|credit|remittance|foreign|investment|banking|bank|department|division|unit|section|office|company|ministry|government|corporation", WEAK),
        ("au_officer_of", "officer|auditor|director|manager|governor|minister|president|accountant ..1 of|at|in ..4 bank|ministry|government|corporation|company|plc|ltd|treasury|authority|commission|foundation|committee", WEAK),
    ],
    "affiliation_internal": [
        ("ai_dept_role", "hr|finance|payroll|accounts|accounting|helpdesk|help|service|security|network|system|systems|mail|webmail|admin*|billing|procurement|legal|compliance|operations|technical|executive|domain|email ..1 department|dept|team|desk|administrator*|staff|office|division|unit|group", STRONG),
        ("ai_it_dept", "=IT|ICT|HR ..1 department|dept|team|desk|administrator*|staff|office|support|helpdesk|service|services", STRONG),
        ("ai_this_is_from", "this|here is|'s ..3 from|with ..2 finance|hr|payroll|accounts|accounting|security|support|helpdesk|admin*|procurement|legal|compliance|operations|management|marketing|sales|facilities|engineering|treasury", STRONG),
        ("ai_this_is_from_it", "this|here is|'s ..3 from|with ..2 =IT|ICT|HR", STRONG),
        ("ai_i_am_from", "i am|'m|are ..4 from|with ..2 ?the ..1 finance|hr|payroll|accounts|accounting|security|support|helpdesk|admin*|procurement|legal|compliance|operations|management|marketing|sales|facilities|engineering|treasury", STRONG),
        ("ai_i_am_from_it", "i am|'m|are ..4 from|with ..2 ?the ..1 =IT|ICT|HR", STRONG),
        ("ai_your_team", "your ..1 it|hr|finance|payroll|helpdesk|help|security|support|admin*|system*|network*|email|mail|service ..1 department|team|desk|administrator|staff|office|provider|support", STRONG),
        ("ai_title_dept", "director|manager|head|chief|officer|assistant|vp|lead ..1 of|to ?the ..1 hr|finance|payroll|accounts|operations|procurement|legal|compliance|ceo|cfo|coo|cto|president", WEAK),
        ("ai_title_dept_it", "director|manager|head|chief|officer|assistant|vp|lead ..1 of|to ?the ..1 =IT|ICT|HR", WEAK),
        ("ai_staff_of", "i am|'m ..2 staff|employee ..1 of|at|with", STRONG),
        ("ai_system_admin", "system|network|mail|email|web|database|server|domain administrator*|admin", WEAK),
        ("ai_dept_alone", "finance|payroll|accounts|security|helpdesk|procurement|compliance department|dept|team|desk", WEAK),
    ],
    "signature_contact": [
        ("sc_street_zip", "# ..4 street|st|avenue|ave|road|rd|blvd|boulevard|drive|dr|lane|ln|way ..6 #", STRONG),
        ("sc_street", "# ..4 street|st|avenue|ave|road|rd|blvd|boulevard|drive|dr|lane|ln|way", WEAK),
        ("sc_in_error", "received|receiving ..4 in error", WEAK),
        ("sc_notify_sender", "notify|inform|contact ..1 the sender", WEAK),
        ("sc_copyright", "© ..2 #", WEAK),
        ("sc_sent_by", "sent|delivered ..1 to ..4 by", WEAK),
        ("sc_receiving", "you|this ..2 receiving|received|sent ..3 because|from|by", WEAK),
    ],
    "affiliation_external": [
        ("ae_sent_by_org", "message|email|mail|notice|notification ..1 from|by @ORG", STRONG),
        ("ae_on_behalf", "on ..1 behalf ..1 of|from ..2 @ORG", STRONG),
    ],
}

# Role and cue words used by the entity rules in extractor.py.
TITLE_WORDS = frozenset((
    "ceo cfo coo cto president chairman chairwoman director manager officer auditor accountant attorney barrister "
    "lawyer secretary minister governor commissioner supervisor administrator controller treasurer executive chief head"
).split())

# An organisation name followed or preceded by one of these is a claim about who is writing.
ORG_CUES = frozenset((
    "team department dept security support customer service services billing account accounts helpdesk desk centre "
    "center online notification notifications bank banking promotions promotion division office group foundation "
    "council organisation organization committee ministry commission agency authority inc ltd llc plc corp "
    "corporation company co sa gmbh representative representatives unit staff"
).split())

# Organisations that spaCy often misses and that attackers imitate. Data only; Phase 8 adds their real domains.
KNOWN_ORGS = (
    "PayPal", "eBay", "Amazon", "Apple", "Microsoft", "Google", "Facebook", "Netflix", "DocuSign", "Dropbox",
    "LinkedIn", "WhatsApp", "Instagram", "Adobe", "Zoom", "DHL", "FedEx", "UPS", "USPS", "IRS", "Chase",
    "Wells Fargo", "Bank of America", "Citibank", "HSBC", "Barclays", "Santander", "Lloyds", "NatWest",
    "Western Union", "GoDaddy", "Yahoo", "Outlook", "Office 365", "Visa", "Mastercard", "American Express",
    "Capital One", "USAA", "SunTrust", "Regions", "Moneybookers", "Skrill", "Alibaba", "Trust Wallet", "Coinbase",
    "Binance", "Steam", "Spotify", "Walmart", "Target", "Costco", "AT&T", "Verizon", "Comcast",
)

# Words that open the closing lines of an email; a name right after one is a signature.
SIGNOFF_WORDS = frozenset((
    "regards sincerely cheers thanks thank best yours truly faithfully respectfully cordially warmly"
).split())

# Words that mark contact details in a signature or footer.
CONTACT_LABELS = frozenset("tel telephone phone mobile cell fax email e-mail contact whatsapp skype call".split())

# Words that name a department, for the department attribute of a claim.
DEPARTMENT_WORDS = frozenset((
    "it ict hr finance payroll accounts accounting helpdesk security support procurement legal compliance operations "
    "marketing sales engineering treasury billing"
).split())

# Spans spaCy sometimes tags as organisations that are placeholders or greetings, never organisations.
NOT_ORGS = frozenset("email url file domain friend dear sir madam customer user member client hello hi hey regards thanks".split())

# A span of an organisation rule made only of these is not a name ("Bank", "Bank account", "Security Company").
GENERIC_WORDS = ORG_CUES | NOT_ORGS | TITLE_WORDS | frozenset("the of in a an and for to at".split())
