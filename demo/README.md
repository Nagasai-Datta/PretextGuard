# demo/

Made-up emails for trying PretextGuard by hand: load them in the interface, read the score and the findings, and see what each check does. Nothing in the project reads this folder (no script and no test), and the interface's built-in "Load an example" menu is separate.

**Everything here is invented.** The people, the companies (Halcyon Freight, Harbour Freight Supply), the addresses and the account numbers are made up. The two bank numbers (IBANs) are public documentation examples, and the links use `example.net`, a domain reserved for examples. No file holds an attachment or a real link, and nobody should send mail to these addresses.

## How to use them

1. Start the API and the interface (see `frontend/README.md`): `python -m src.api.main` in one terminal, `npm run preview` in `frontend/` in another, then open <http://127.0.0.1:4173>.
2. **One email:** choose "One email", press "Load a .eml file" and pick a file from this folder. Leave "Organisation domain" empty: the recipient's address (`halcyonfreight.com`) is used. Press Analyse.
3. **A thread:** choose "A thread", press "Add .eml files" and pick the files of `thread_supplier_payment/` (see below). The order does not matter: the newest message by its `Date` header is judged against the others.

From the terminal, without the interface:

```bash
python -m src.router.pipeline demo/bad_01_wire_request_from_gmail.eml
python -m src.router.pipeline --thread demo/thread_supplier_payment/0[1-4]_*.eml demo/thread_supplier_payment/05_HIJACK_new_bank_account_marta.eml
```

## Single emails

The bands below come from the rule engine. The tactic model adds at most 12 points to a score (more only when a contradiction is already there and the text is urgent or secretive), so a "Low risk" file stays Low whatever the model says, and a file that is at least "Suspicious" stays at least Suspicious. The exact number you see depends on the tactic model.

| File | What it is | Band | What to look at |
|---|---|---|---|
| `bad_01_wire_request_from_gmail.eml` | A wire request with urgency and secrecy that claims to come from the company's Finance Director, but is written from a free `gmail.com` address | Suspicious to High risk | SPF, DKIM and DMARC all pass (for gmail.com). The claim "I am the Finance Director of Halcyon Freight" is what the headers contradict |
| `bad_02_ceo_gift_cards_lookalike_domain.eml` | A "CEO" asks for gift cards and says to keep it between us, from `halcyonfre1ght.com` (a digit 1 in place of the letter i) | High risk | The look-alike domain authenticates perfectly as itself. Only the claim checked against the real organisation domain exposes it |
| `bad_03_it_password_forged_company_domain.eml` | "IT Security" asks you to confirm your password, with the company's own address in From, but the sender's SPF and DMARC checks failed | High risk | A forged sender: the authentication verdicts are read from the receiving server's header and contradict the claim of being internal |
| `bad_04_payroll_bank_details_from_outlook.eml` | "HR Payroll" asks for your new bank details before payday, from `outlook.com`, with a Reply-To to yet another domain | High risk | A request for private data from a free mailbox that claims to be internal, plus the Reply-To redirect |
| `bad_05_supplier_invoice_new_bank_reply_to_gmail.eml` | A supplier's invoice with "our bank has changed" and a Reply-To to a `gmail.com` address | Suspicious to High risk | The supplier's domain is genuine and authenticates. The signals are the Reply-To that leaves the domain and the changed payment details (a bank-detail change can only be judged against the thread, see below) |
| `bad_06_paypal_lookalike_confirm_password.eml` | "PayPal Service" asks you to confirm your password, from `paypa1.com` | Suspicious to High risk | An outside organisation claim against a look-alike of its real domain |
| `good_01_finance_director_same_request_company_domain.eml` | **The same request as `bad_01`**, almost word for word, from the Finance Director's own company address with passing authentication | Low risk | Same words, different evidence: the claim is consistent, so the urgent and confidential tone alone does not raise an alarm |
| `good_02_supplier_question_about_purchase_order.eml` | An ordinary question from a supplier whose domain authenticates | Low risk | An outside organisation is not suspicious by itself |
| `good_03_mailing_list_digest.eml` | A mailing-list digest with `List-Id` and `List-Unsubscribe` | Low risk | List mail is recognised and not judged as a personal claim |
| `good_04_colleague_urgent_but_ordinary.eml` | A colleague says "it is a bit urgent" about the usual customs forms | Low risk | Urgency without a contradiction adds a few points at most |

Reading tip: open `bad_01` and `good_01` one after the other. The score difference comes from the headers, not from the words.

## The thread: `thread_supplier_payment/`

One supplier conversation about invoice 4471. Messages 01 to 04 are an ordinary exchange: Marta (Harbour Freight Supply) sends the invoice with the usual bank account, Ivan (Halcyon Freight) asks about delivery and the return fee, and so on. There are two possible fifth messages, from Marta's address:

| Files to add | Band | What it shows |
|---|---|---|
| `01` to `04` | Low risk | A calm thread. The scan finds no point where it flipped |
| `01` to `04` and `05_honest_follow_up_marta.eml` | Low risk | A normal reply: no false alarm |
| `01` to `04` and `05_HIJACK_new_bank_account_marta.eml` | Suspicious to High risk | The same real address, passing SPF, DKIM and DMARC, now gives a **different bank account** (`DE89...`, the thread used `GB82...`), asks to pay today, asks for secrecy, and sends from a mail program it never used before. The message is marked as the point where the thread flipped (message 5) |

This is the case no single-message check can see: the account is genuine, so every authentication check passes, and only the conversation history gives it away. It is also the project's N2 idea (the thread verifier, master document Section 8.17).

## If a result differs from this table

The table was checked with the project's own analysis code, with a stand-in for the tactic model (the trained model lives only on the author's Mac). If a file lands in a different band on your machine, that is a finding: note the file, the score and the findings table, and either fix the table or the file.
