import type { Refusal } from './types'

// Identity is simulated: the chosen persona is sent as X-User-Id on every request. The
// server decides what that person may see and change; nothing here is a security control.

/** A refusal from the server (401 or 403), carried so the UI can show the reason. */
export class RefusedError extends Error {
  readonly refusal: Refusal
  readonly status: number

  constructor(status: number, refusal: Refusal) {
    super(refusal.reason)
    this.status = status
    this.refusal = refusal
  }
}

export class ApiError extends Error {}

type Options = { method?: 'GET' | 'PUT' | 'POST'; body?: unknown; params?: Record<string, string | number | undefined> }

export async function api<T>(path: string, userId: string | null, options: Options = {}): Promise<T> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(options.params ?? {})) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  const url = `/api/v1${path}${query.size ? `?${query}` : ''}`
  const headers: Record<string, string> = {}
  if (userId) headers['X-User-Id'] = userId
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  const response = await fetch(url, {
    method: options.method ?? 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  const payload: unknown = await response.json().catch(() => null)

  if (response.status === 401 || response.status === 403) {
    throw new RefusedError(response.status, payload as Refusal)
  }
  if (!response.ok) {
    const detail = (payload as { detail?: unknown } | null)?.detail
    throw new ApiError(typeof detail === 'string' ? detail : `request failed (${response.status})`)
  }
  return payload as T
}
