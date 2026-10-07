"""Word and phrase lists for the keyword baseline: seven tactics, two strengths each.

This file is data only. keywords.py reads it, normalises every phrase the same way
it normalises an email, and does the matching.

How to read a list:
    "strong"  a phrase that almost only appears when the tactic is being used
              ("keep this between us"). One strong phrase is enough to fire the tactic.
    "weak"    a phrase that suggests the tactic but also appears in ordinary mail
              ("urgently", "valued customer"). Two different weak phrases fire the tactic.

Writing rules:
- Write phrases in plain lowercase or normal text. Apostrophes, case and punctuation do not
  matter: "don't", "Don't" and "don ' t" all match the same email text. A placeholder
  such as [URL] may be part of a phrase.
- A phrase must not sit inside another phrase of the same tactic ("between us" inside
  "just between us"): the shorter one would count the same words twice. keywords.py
  refuses to load a lexicon that does this.
- Bare job titles are left out of "authority" on purpose: every signature has one.
  Only phrases that assert rank or institutional power are used.
- The lists come from the tactic definitions in master document Section 7 and from general
  knowledge of how business email compromise, phishing and advance-fee fraud are worded.
  They were written fresh for this project. After the first run they may be revised by looking
  at the train split only (never validation or test); LEXICON_VERSION records each revision.

Known limits, stated in the report: no negation ("there is no rush" still matches "rush"
phrases), no misspellings, no paraphrase. Those are the gaps a learned model should close.
"""

LEXICON_VERSION = "0.1"

STRONG_WEIGHT = 1.0
WEAK_WEIGHT = 0.5

# Same names as the tactic_* label columns of master document Section 8.7.
TACTICS = ("authority", "urgency", "scarcity", "reciprocity", "social_proof", "liking", "secrecy")

LEXICON = {
    # Asserted rank, role or institutional power.
    "authority": {
        "strong": [
            "this is the ceo", "this is your ceo", "this is the cfo", "this is your cfo",
            "this is the managing director", "this is the president", "this is your manager",
            "i am the ceo", "i am your ceo", "i am the cfo", "i am your cfo",
            "i am the managing director", "i am the chairman", "i am the general manager",
            "as your ceo", "as the ceo", "as your cfo", "as the cfo", "as your manager",
            "on behalf of the ceo", "on behalf of the cfo", "on behalf of the director",
            "on behalf of the management", "on behalf of the board",
            "by order of the", "by order of management",
            "instructed by the ceo", "instructed by the cfo", "instructed by management",
            "authorized by the ceo", "authorised by the ceo", "authorized by management",
            "the ceo has asked", "the ceo has requested", "the cfo has asked", "the cfo has requested",
            "the ceo requires", "the cfo requires", "management requires", "management has requested",
            "management has instructed", "company policy requires", "policy requires you",
            "it security team", "it security department", "it helpdesk team", "it help desk team",
            "it support team", "technical support team", "account security team",
            "account verification team", "security department", "compliance department",
            "fraud prevention team", "fraud department", "human resources department",
            "payroll department", "from the system administrator", "your system administrator",
            "official notice", "this is an official", "internal revenue service",
            "central bank of", "federal bureau of",
        ],
        "weak": [
            "i am the manager", "i am the director", "i am a director", "i am the head of",
            "i am the vice president", "i am the president", "i am the owner", "i am the auditor",
            "i am a barrister", "i am barrister", "i am an attorney", "i am a lawyer",
            "i am the account officer", "i am the chief accountant", "i am a senior",
            "personal assistant to", "senior management", "executive management", "head office",
            "head of department", "board of directors", "mandatory", "compliance",
            "system administrator", "security officer", "account officer", "on behalf of",
            "authorized", "authorised", "legal action", "legal proceedings", "law enforcement",
            "ministry of",
        ],
    },
    # Manufactured deadline or time pressure.
    "urgency": {
        "strong": [
            "urgent action required", "action required immediately", "immediate action required",
            "immediate action", "immediate attention", "immediate response", "respond immediately",
            "reply immediately", "reply asap", "respond asap", "act now", "act immediately",
            "act fast", "act quickly", "do not delay", "dont delay", "without delay",
            "no time to waste", "time is of the essence", "time sensitive",
            "this is urgent", "it is urgent", "very urgent", "extremely urgent", "urgent request",
            "urgent matter", "urgent attention", "urgent response", "urgent reply", "urgent action",
            "urgent assistance", "need this done today", "need it done today", "need this today",
            "need this immediately", "need this asap", "need this urgently", "do this now", "do it now",
            "within 24 hours", "within 48 hours", "within 72 hours", "within 12 hours",
            "within 2 hours", "within 1 hour", "within one hour", "within the hour",
            "within the next 24 hours", "within the next 48 hours", "within the next hour",
            "by the end of today", "by end of day today", "before the end of today",
            "by close of business today", "before close of business today",
            "before it is too late", "deadline is today", "deadline is tomorrow", "expires today",
        ],
        "weak": [
            "urgent", "urgently", "asap", "immediately", "immediate", "right away", "right now",
            "at once", "promptly", "deadline", "hurry", "quickly", "as soon as possible",
            "end of day", "eod", "close of business", "by tonight", "by today", "this afternoon",
            "important notice", "high priority",
        ],
    },
    # Loss or finality framing.
    "scarcity": {
        "strong": [
            "last chance", "final chance", "final notice", "final warning", "last warning",
            "final reminder", "final opportunity", "last opportunity", "one last time",
            "your account will be suspended", "your account will be closed",
            "your account will be deleted", "your account will be terminated",
            "your account will be locked", "your account will be disabled",
            "your account will be limited", "your account has been suspended",
            "your account has been locked", "your account has been limited",
            "your account has been disabled", "account has been compromised",
            "access will be revoked", "access will be suspended", "access will be removed",
            "will be permanently", "permanently deleted", "permanently disabled",
            "permanently closed", "permanently suspended", "permanently locked",
            "lose access", "lose your access", "will lose access", "avoid suspension",
            "avoid account suspension", "avoid permanent", "avoid losing", "avoid being",
            "unless you verify", "unless you confirm", "unless you update", "unless you respond",
            "failure to comply", "failure to respond", "failure to verify", "failure to confirm",
            "failure to update", "if you fail to", "if you do not verify", "if you dont verify",
            "or your account will", "or you will lose", "or else",
            "limited time offer", "limited time only", "limited offer", "offer expires",
            "offer ends", "expires soon", "expiring soon", "ends soon", "while supplies last",
            "only a few left", "only a limited number", "limited number of", "limited availability",
            "dont miss out", "dont miss this", "do not miss out", "do not miss this",
            "once in a lifetime", "last day", "final day",
        ],
        "weak": [
            "will expire", "has expired", "expires", "expiring", "suspended", "suspension",
            "deactivated", "deactivation", "permanently", "penalty", "penalties",
            "limited time", "closure", "forfeit",
        ],
    },
    # Debt framing: "I did something for you, now you owe me".
    "reciprocity": {
        "strong": [
            "i covered for you", "i helped you out", "i helped you", "i did you a favor",
            "i did you a favour", "you owe me", "you owe us", "return the favor", "return the favour",
            "returning the favor", "returning the favour", "pay me back", "repay me",
            "after all i have done for you", "after everything i have done for you",
            "after all i did for you", "after all ive done for you", "i have always been there for you",
            "remember when i helped", "remember the time i", "i did this for you", "i did that for you",
            "i took care of", "i need a favor", "i need a favour", "need a small favor",
            "need a small favour", "need a quick favor", "need a quick favour",
            "do me a favor", "do me a favour", "a favor in return", "a favour in return",
            "in return for your help", "in return for your", "in exchange for your help",
            "as a thank you for", "as a token of appreciation", "a token of our appreciation",
            "free gift", "complimentary gift", "gift for you", "as a gesture of",
        ],
        "weak": [
            "a favor", "a favour", "owe you", "owe me", "in return", "in exchange", "repay",
            "as a gift", "free sample", "complimentary", "my gift to you", "thank you in advance for",
        ],
    },
    # Everyone else has already done it.
    "social_proof": {
        "strong": [
            "everyone else has already", "everyone has already", "everybody has already",
            "the whole team has already", "the entire team has already", "the rest of the team has already",
            "the rest of the team has", "your colleagues have already", "your coworkers have already",
            "your co workers have already", "other employees have already", "other employees have completed",
            "all employees have already", "all staff have already", "all other staff", "other members of staff have",
            "your team members have already", "most of your colleagues", "most of our customers",
            "thousands of customers", "thousands of satisfied", "thousands of people",
            "millions of people", "millions of users", "millions of satisfied", "join thousands",
            "join millions", "join the thousands", "trusted by thousands", "trusted by millions",
            "everyone is doing it", "everybody is doing it", "others have already",
            "already completed by", "already signed off", "has already signed off",
            "already approved by", "already been approved by", "already done by",
        ],
        "weak": [
            "everyone else", "all employees", "all staff", "other employees", "your colleagues",
            "your coworkers", "thousands of", "millions of", "satisfied customers",
            "happy customers", "most people", "testimonials", "bestselling", "best selling",
            "popular choice", "everybody",
        ],
    },
    # Manufactured warmth, flattery, false familiarity.
    "liking": {
        "strong": [
            "dear friend", "my dear friend", "my good friend", "dear beloved", "beloved in the lord",
            "dearest one", "my dearest", "dear beloved friend", "great seeing you", "great to see you",
            "great meeting you", "nice meeting you", "nice seeing you", "good seeing you",
            "it was great to see you", "it was great meeting you", "it was a pleasure meeting you",
            "i have heard so much about you", "i have heard great things about you",
            "i have always admired", "i am a big fan", "i came across your profile",
            "i came across your", "i found your profile", "i got your contact from",
            "you have been highly recommended", "you were highly recommended", "you were recommended to me",
            "you are the best", "you are amazing", "you are such a", "you are a wonderful",
            "your excellent work", "your great work", "your hard work", "we appreciate you",
            "we value you", "friendship", "be your friend", "friends forever", "god bless you",
            "god will bless you", "may god bless", "dear valued", "as a valued customer",
            "as a valued member", "our valued customer", "our valued member",
        ],
        "weak": [
            "hope you are well", "hope you are doing well", "hope you are doing great",
            "hope you are having a great", "hope this email finds you well", "hope this finds you well",
            "i hope you are well", "i hope you are doing well", "i trust you are well",
            "i trust this finds you well", "valued customer", "valued member", "my friend",
            "dear sir or madam", "buddy", "pal", "god bless", "blessings", "i admire",
        ],
    },
    # Cut the victim off from verification.
    "secrecy": {
        "strong": [
            "keep this between us", "keep it between us", "keep this confidential",
            "keep it confidential", "keep this to yourself", "keep it to yourself",
            "keep this private", "keep it private", "keep this secret", "keep it secret",
            "keep this quiet", "keep it quiet", "keep this strictly", "keep this a secret",
            "dont tell anyone", "do not tell anyone", "dont tell anybody", "do not tell anybody",
            "dont tell your", "do not tell your", "dont share this with", "do not share this with",
            "do not share this", "dont share this", "do not discuss this", "dont discuss this",
            "do not discuss it", "dont discuss it", "do not mention this", "dont mention this",
            "do not mention it", "dont mention it", "do not inform anyone", "dont inform anyone",
            "dont loop in", "do not loop in", "dont involve", "do not involve",
            "dont copy anyone", "do not copy anyone", "dont cc", "do not cc", "do not forward this",
            "dont forward this", "do not forward it", "dont forward it",
            "without telling anyone", "without informing anyone", "without anyone knowing",
            "without anybody knowing", "nobody should know", "no one should know",
            "no one else should know", "no one else needs to know", "nobody else needs to know",
            "no one else must know", "nobody else must know",
            "just between us", "between you and me", "between the two of us", "for your eyes only",
            "top secret", "highly confidential", "dont contact your", "do not contact your",
            "dont call your", "do not call your", "dont speak to anyone", "do not speak to anyone",
            "dont talk to anyone", "do not talk to anyone", "dont speak with anyone",
            "dont verify with", "do not verify with",
            "absolute confidentiality", "utmost confidentiality", "total confidentiality",
            "complete confidentiality", "strict confidentiality", "in strict confidence",
            "absolute secrecy", "utmost secrecy", "total secrecy", "complete secrecy", "strict secrecy",
        ],
        "weak": [
            "strictly confidential", "confidential matter", "confidential", "confidentially",
            "secret", "secretly", "discreet", "discreetly", "discretion", "privately",
            "private matter", "quietly", "personal matter", "dont forward", "do not forward",
            "do not disclose", "dont disclose", "not to disclose", "do not reveal", "dont reveal",
        ],
    },
}
