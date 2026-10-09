import { useMemo, useState } from 'react'
import { EXAMPLES } from '../lib/examples.js'
import { byteLength, formatBytes, MAX_EMAIL_BYTES, MAX_THREAD_BYTES, MAX_THREAD_MESSAGES } from '../lib/limits.js'

let nextId = 1
export const newMessage = (text = '', name = '') => ({ id: nextId++, text, name })

// A file is read in the browser as text; it is never uploaded as a file and attachments are never opened (the API reads text only).
async function readEmailFile(file) {
  if (file.size > MAX_EMAIL_BYTES) {
    throw new Error(`${file.name}: ${formatBytes(file.size)} is over the limit of ${formatBytes(MAX_EMAIL_BYTES)} for one email.`)
  }
  return file.text()
}

function FileButton({ label, multiple, onFiles, disabled }) {
  return (
    <label className={`btn focus-within:outline-2 ${disabled ? 'opacity-50' : ''}`}>
      {label}
      <input
        type="file"
        className="sr-only"
        accept=".eml,.txt,.mbox,message/rfc822,text/plain"
        multiple={multiple}
        disabled={disabled}
        onChange={(event) => {
          const files = Array.from(event.target.files || [])
          event.target.value = ''
          if (files.length) onFiles(files)
        }}
      />
    </label>
  )
}

export default function EmailInput({
  mode,
  onMode,
  email,
  onEmail,
  messages,
  onMessages,
  orgDomain,
  onOrgDomain,
  wantExplain,
  onWantExplain,
  onSubmit,
  onClear,
  busy,
  retryLeft,
  problem,
}) {
  const [fileError, setFileError] = useState(null)
  const [note, setNote] = useState(null)

  const emailBytes = useMemo(() => byteLength(email), [email])
  const threadBytes = useMemo(() => messages.reduce((sum, m) => sum + byteLength(m.text), 0), [messages])

  const loadExample = (id) => {
    const example = EXAMPLES.find((e) => e.id === id)
    if (!example) return
    setFileError(null)
    setNote(example.note)
    onOrgDomain(example.orgDomain || '')
    if (example.kind === 'thread') {
      onMode('thread')
      onMessages(example.messages.map((text, i) => newMessage(text, `Message ${i + 1}`)))
    } else {
      onMode('email')
      onEmail(example.email)
    }
  }

  const loadOne = async (files) => {
    setFileError(null)
    try {
      onEmail(await readEmailFile(files[0]))
      setNote(null)
    } catch (error) {
      setFileError(error.message)
    }
  }

  const addFiles = async (files) => {
    setFileError(null)
    const room = MAX_THREAD_MESSAGES - messages.length
    if (files.length > room) setFileError(`A thread can have at most ${MAX_THREAD_MESSAGES} messages; only the first ${Math.max(room, 0)} files were added.`)
    const added = []
    for (const file of files.slice(0, Math.max(room, 0))) {
      try {
        added.push(newMessage(await readEmailFile(file), file.name))
      } catch (error) {
        setFileError(error.message)
      }
    }
    if (added.length) {
      const kept = messages.length === 1 && !messages[0].text.trim() ? [] : messages
      onMessages([...kept, ...added])
      setNote(null)
    }
  }

  const changeMessage = (id, text) => onMessages(messages.map((m) => (m.id === id ? { ...m, text } : m)))
  const removeMessage = (id) => onMessages(messages.filter((m) => m.id !== id))

  return (
    <form
      className="card"
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div role="group" aria-label="What to analyse" className="flex gap-1">
          <button type="button" className="tab" aria-current={mode === 'email' ? 'page' : undefined} onClick={() => onMode('email')}>
            One email
          </button>
          <button type="button" className="tab" aria-current={mode === 'thread' ? 'page' : undefined} onClick={() => onMode('thread')}>
            A thread
          </button>
        </div>
        <label className="flex w-full min-w-0 items-center gap-2 text-sm sm:ml-auto sm:w-auto">
          <span className="hint">Example</span>
          <select
            className="input min-w-0 flex-1 sm:w-auto sm:max-w-md"
            value=""
            onChange={(event) => {
              loadExample(event.target.value)
            }}
            aria-label="Load an example email"
          >
            <option value="">Load an example...</option>
            {EXAMPLES.map((example) => (
              <option key={example.id} value={example.id}>
                {example.title}
              </option>
            ))}
          </select>
        </label>
      </div>

      {note && <p className="hint mb-3">{note}</p>}

      {mode === 'email' ? (
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <label htmlFor="email-text" className="font-medium">
              The email, with its headers if you have them
            </label>
            <span className="ml-auto" />
            <FileButton label="Load a .eml file" onFiles={loadOne} disabled={busy} />
          </div>
          <textarea
            id="email-text"
            className="input mono"
            rows={14}
            spellCheck={false}
            autoComplete="off"
            autoCapitalize="off"
            value={email}
            onChange={(event) => onEmail(event.target.value)}
            placeholder={'From: Name <name@example.com>\nTo: you@yourcompany.com\nSubject: ...\n\nThe text of the email...'}
          />
          <p className="hint mt-1">
            {formatBytes(emailBytes)} of {formatBytes(MAX_EMAIL_BYTES)}. A body pasted without headers works, but then nothing about the sender can be checked.
          </p>
        </div>
      ) : (
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <p className="hint m-0 flex-1">
              The messages of one conversation, in any order: the newest (by its Date header) is judged against the earlier ones. {messages.length} of{' '}
              {MAX_THREAD_MESSAGES} messages, {formatBytes(threadBytes)} of {formatBytes(MAX_THREAD_BYTES)}.
            </p>
            <FileButton label="Add .eml files" multiple onFiles={addFiles} disabled={busy || messages.length >= MAX_THREAD_MESSAGES} />
            <button type="button" className="btn" disabled={busy || messages.length >= MAX_THREAD_MESSAGES} onClick={() => onMessages([...messages, newMessage()])}>
              Add a message
            </button>
          </div>
          <ol className="m-0 flex list-none flex-col gap-3 p-0">
            {messages.map((message, index) => (
              <li key={message.id} className="rounded-lg border border-line p-3">
                <div className="mb-1 flex items-center gap-2">
                  <label htmlFor={`message-${message.id}`} className="font-medium">
                    Message {index + 1}
                  </label>
                  {message.name && <span className="hint truncate">{message.name}</span>}
                  <span className="hint ml-auto">{formatBytes(byteLength(message.text))}</span>
                  <button type="button" className="btn" onClick={() => removeMessage(message.id)} disabled={busy}>
                    Remove
                  </button>
                </div>
                <textarea
                  id={`message-${message.id}`}
                  className="input mono"
                  rows={7}
                  spellCheck={false}
                  autoComplete="off"
                  value={message.text}
                  onChange={(event) => changeMessage(message.id, event.target.value)}
                />
              </li>
            ))}
          </ol>
        </div>
      )}

      {fileError && (
        <p role="alert" className="mt-2 text-sm text-critical">
          {fileError}
        </p>
      )}

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div>
          <label htmlFor="org-domain" className="font-medium">
            Your organisation's domain (optional)
          </label>
          <input
            id="org-domain"
            className="input mt-1"
            value={orgDomain}
            onChange={(event) => onOrgDomain(event.target.value)}
            placeholder="acmecorp.com"
            spellCheck={false}
            autoComplete="off"
          />
          <p className="hint mt-1">Lets the checks tell whether the sender claims to be from inside your organisation. Empty: the domain of the To header is used.</p>
        </div>
        <div className="flex flex-col justify-end gap-2">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={wantExplain} onChange={(event) => onWantExplain(event.target.checked)} />
            <span>Also find the words behind the tactics (a second or more; the score does not depend on it)</span>
          </label>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button type="submit" className="btn btn-primary" disabled={busy || Boolean(problem) || retryLeft > 0}>
          {busy ? (
            <>
              <span className="spinner" aria-hidden="true" /> Working...
            </>
          ) : retryLeft > 0 ? (
            `Try again in ${retryLeft} s`
          ) : (
            'Analyze'
          )}
        </button>
        <button type="button" className="btn" onClick={onClear} disabled={busy}>
          Clear
        </button>
        {problem && (
          <span className="text-sm text-critical" role="status">
            {problem}
          </span>
        )}
      </div>
    </form>
  )
}
