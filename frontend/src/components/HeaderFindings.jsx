// The facts read from the email's headers, which the header and request verifiers used. SPF, DKIM and DMARC are read from the receiving server's
// Authentication-Results header, never recomputed. They prove which domain sent the message, not who the person is.
const LABELS = [
  ['headers_found', 'Header block found'],
  ['from_name', 'Display name'],
  ['from_domain', 'Sending domain (From)'],
  ['reply_domain', 'Reply-To domain'],
  ['reply_to_divergence', 'Replies go to another domain'],
  ['spf', 'SPF'],
  ['dkim', 'DKIM'],
  ['dmarc', 'DMARC'],
  ['auth_state', 'Authentication state'],
  ['authenticated_domain', 'Domain that authenticated'],
  ['freemail', 'Free mailbox provider'],
  ['list_mail', 'Mailing-list mail'],
  ['name_address', 'Display name shows an address'],
  ['name_domain', 'Domain shown in the display name'],
  ['envelope_mismatch', 'Envelope sender differs'],
  ['org_domain', 'Your organisation domain'],
  ['org_checkable', 'Organisation claims checkable'],
  ['from_matches_org', 'Sender is your organisation'],
  ['org_lookalike_score', 'Look-alike score against your domain'],
]

function show(value) {
  if (value === null || value === undefined) return 'not known'
  if (value === true) return 'yes'
  if (value === false) return 'no'
  return String(value)
}

export default function HeaderFindings({ findings }) {
  const known = LABELS.filter(([key]) => key in findings)
  return (
    <section className="card" aria-labelledby="headers-title">
      <details open={findings.headers_found}>
        <summary id="headers-title" className="font-semibold">
          What the headers say
        </summary>
        {!findings.headers_found && <p className="mt-2">No header block was found, so there is no sender evidence. Paste the whole email with its headers.</p>}
        <dl className="mt-2 grid grid-cols-1 gap-x-8 gap-y-1 text-sm sm:grid-cols-[auto_1fr] md:grid-cols-[auto_1fr_auto_1fr]">
          {known.map(([key, label]) => (
            <div key={key} className="contents">
              <dt className="text-ink2">{label}</dt>
              <dd className="m-0 [overflow-wrap:anywhere]">{show(findings[key])}</dd>
            </div>
          ))}
        </dl>
        <p className="hint m-0 mt-2">
          Attackers write headers too. The checks use them only to test a claim the email makes, and a pass means "this domain sent it", not "this person is who they say".
        </p>
      </details>
    </section>
  )
}
