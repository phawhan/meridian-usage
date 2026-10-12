import { RefusedError } from '../api/client'

/** Shows why the server said no. Never a blank screen: a refusal is an answer. */
export function RefusalBanner({ error }: { error: unknown }) {
  if (error instanceof RefusedError) {
    const { refusal } = error
    return (
      <div className="banner banner-denied" role="alert">
        <strong>{refusal.error === 'unauthenticated' ? 'Not signed in.' : 'Not allowed.'}</strong>{' '}
        {refusal.reason}
        {'required_scope' in refusal && refusal.required_scope && (
          <span className="muted"> (needs the {refusal.required_scope} scope)</span>
        )}
      </div>
    )
  }
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <div className="banner banner-error" role="alert">
      {message}
    </div>
  )
}
