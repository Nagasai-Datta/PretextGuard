"""The label vocabulary and sampling constants shared by every Phase 5 script.

One place defines what a tactic is, what a claim type is, how big a batch is and how an email is shown
to an annotator, so batches.py, prompts.py, validate_labels.py, agreement.py, labels.py and
synthetic.py can never disagree about them.

TACTICS are the seven manipulation tactics of master document Section 7, named like the tactic_*
label columns (Section 8.7). CLAIM_TYPES are the eleven claim types of the routing table
(Section 6.4). The definitions below are the exact words the annotators and the synthetic-email
generator are given.
"""

TACTICS = ("authority", "urgency", "scarcity", "reciprocity", "social_proof", "liking", "secrecy")

CLAIM_TYPES = (
    "affiliation_internal", "affiliation_external", "authority", "reply_direction", "signature_contact",
    "prior_relationship", "payment_request", "payment_change", "credential_request", "gift_card", "data_request",
)

ANNOTATORS = ("gemini", "deepseek")  # the two main annotators, one chat service each
TIEBREAKER = "zai"                   # z.ai (GLM): only sees emails the two main annotators disagree on
ALL_ANNOTATORS = ANNOTATORS + (TIEBREAKER,)

BATCH_SIZE = 20          # emails per chat message
MAX_EMAIL_CHARS = 2000   # about what DistilBERT's 512 tokens can read, so annotators see what the model sees
MIN_WORDS = 8            # shorter emails are not sampled: too little text to carry a tactic or a claim
MAX_CLAIMS = 12          # per email; more than this in one reply is treated as a runaway answer
MAX_SPAN_CHARS = 300

TACTIC_DEFINITIONS = {
    "authority": "The email asserts rank, role or institutional power to make the reader comply "
                 "(\"This is the CFO\", \"IT Security requires\"). Mentioning a job title in passing is not enough.",
    "urgency": "Manufactured deadline or time pressure (\"before 3 PM today\", \"immediately\").",
    "scarcity": "Loss or finality framing: a last chance, or something will be lost, closed or deleted "
                "(\"last chance\", \"your account will be deleted\"). An email can be both urgent and scarce.",
    "reciprocity": "Debt framing: the sender did something for the reader, or offers a gift or favour, "
                   "so the reader owes something (\"I covered for you last month, now I need ...\").",
    "social_proof": "Everyone else has already done it (\"the whole team has already signed off\").",
    "liking": "Manufactured warmth, flattery or false familiarity (\"Great seeing you at the offsite, quick favour ...\").",
    "secrecy": "Cuts the reader off from checking or asking anyone else (\"keep this between us\", "
               "\"don't loop in your manager\").",
}

CLAIM_DEFINITIONS = {
    "affiliation_internal": "The sender says they belong to the reader's own organisation or one of its departments "
                            "(\"this is David from Finance\", \"IT help desk\", \"HR team\").",
    "affiliation_external": "The sender says they represent an outside organisation (a bank, vendor, agency, "
                            "\"PayPal Security Team\", \"Central Bank\").",
    "authority": "The sender claims a rank or role that gives them power (\"as CFO\", \"I am the Director of Operations\").",
    "reply_direction": "The sender tells the reader to reply or contact them somewhere other than this email, "
                       "or only them (\"reply to my personal email\", \"text me on this number\").",
    "signature_contact": "A signature or footer gives contact details (an email address or phone number with a name or title).",
    "prior_relationship": "The sender claims an earlier meeting, conversation or agreement "
                          "(\"as we discussed\", \"great seeing you at the offsite\").",
    "payment_request": "The sender asks for money to be sent or an invoice or bill to be paid.",
    "payment_change": "The sender asks to change bank, payment or payroll details, or the payee.",
    "credential_request": "The sender asks for a password, login, verification code, or to sign in or verify an account.",
    "gift_card": "The sender asks the reader to buy, send or photograph gift cards.",
    "data_request": "The sender asks for personal, financial, employee or company data or documents "
                    "(tax forms, staff lists, ID copies).",
}

assert set(TACTIC_DEFINITIONS) == set(TACTICS) and set(CLAIM_DEFINITIONS) == set(CLAIM_TYPES)


def prepare_text(body):
    """The text an annotator sees for one email: capped, with angle brackets neutralised.

    Angle brackets become single guillemets so email text can never contain a tag that looks like
    the <email> wrapper (prompt injection). Text over MAX_EMAIL_CHARS is cut at a word boundary.
    """
    text = body.strip() if isinstance(body, str) else ""
    if len(text) > MAX_EMAIL_CHARS:
        text = text[:MAX_EMAIL_CHARS].rsplit(" ", 1)[0] + " [TRUNCATED]"
    return text.replace("<", "‹").replace(">", "›")
