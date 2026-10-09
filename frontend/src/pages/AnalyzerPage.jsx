import { useRef, useState } from 'react'
import EmailInput, { newMessage } from '../components/EmailInput.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Results from '../components/Results.jsx'
import { domainProblem, emailProblem, threadProblem } from '../lib/limits.js'
import { useAnalysis, useRetryTimer } from '../lib/useAnalysis.js'

// The analyzer page owns what the person typed; useAnalysis owns the calls. The page stays mounted when the dashboard is shown, so a result is not lost.
export default function AnalyzerPage() {
  const [mode, setMode] = useState('email')
  const [email, setEmail] = useState('')
  const [messages, setMessages] = useState(() => [newMessage()])
  const [orgDomain, setOrgDomain] = useState('')
  const [wantExplain, setWantExplain] = useState(true)
  const [attempted, setAttempted] = useState(false)
  const lastRequest = useRef(null)
  const analysis = useAnalysis()
  const retryLeft = useRetryTimer(analysis.error)
  const explainRetryLeft = useRetryTimer(analysis.explainError)

  const inputProblem = () => (mode === 'thread' ? threadProblem(messages) : emailProblem(email)) || domainProblem(orgDomain)
  const hasText = mode === 'thread' ? messages.some((m) => m.text.trim()) : email.trim() !== ''
  const problem = attempted || hasText || orgDomain.trim() ? inputProblem() : null

  const submit = () => {
    if (inputProblem()) {
      setAttempted(true)
      return
    }
    const request =
      mode === 'thread'
        ? { kind: 'thread', messages: messages.map((m) => m.text), orgDomain }
        : { kind: 'email', email, orgDomain }
    lastRequest.current = request
    analysis.run(request, wantExplain)
  }

  const clear = () => {
    analysis.reset()
    lastRequest.current = null
    setEmail('')
    setMessages([newMessage()])
    setOrgDomain('')
    setAttempted(false)
  }

  const report = analysis.report
  const explainStatus = !report
    ? 'off'
    : report.explained || analysis.explainDone
      ? 'done'
      : analysis.phase === 'explaining'
        ? 'working'
        : analysis.explainError
          ? 'failed'
          : 'off'

  return (
    <div className="flex flex-col gap-4">
      <EmailInput
        mode={mode}
        onMode={setMode}
        email={email}
        onEmail={setEmail}
        messages={messages}
        onMessages={setMessages}
        orgDomain={orgDomain}
        onOrgDomain={setOrgDomain}
        wantExplain={wantExplain}
        onWantExplain={setWantExplain}
        onSubmit={submit}
        onClear={clear}
        busy={analysis.busy}
        retryLeft={retryLeft}
        problem={problem}
      />
      <div aria-live="polite">
        {analysis.phase === 'analyzing' && (
          <p className="m-0 flex items-center gap-2">
            <span className="spinner" aria-hidden="true" /> Checking the claims against the evidence...
          </p>
        )}
      </div>
      <ErrorBanner error={analysis.error} />
      {report && (
        <Results
          report={report}
          explainStatus={explainStatus}
          explainError={analysis.explainError}
          explainRetryLeft={explainRetryLeft}
          onExplain={() => lastRequest.current && analysis.explainReport(lastRequest.current)}
        />
      )}
    </div>
  )
}
