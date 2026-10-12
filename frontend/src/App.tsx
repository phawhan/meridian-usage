import { useQuery } from '@tanstack/react-query'

type Health = { status: string; environment: string }

async function fetchHealth(): Promise<Health> {
  const response = await fetch('/api/v1/healthz')
  if (!response.ok) throw new Error(`healthz returned ${response.status}`)
  return response.json() as Promise<Health>
}

export default function App() {
  const health = useQuery({ queryKey: ['healthz'], queryFn: fetchHealth })

  return (
    <main>
      <h1>Meridian usage admin</h1>
      {health.isPending && <p>Connecting to the usage service…</p>}
      {health.isError && <p role="alert">Usage service unreachable: {health.error.message}</p>}
      {health.data && (
        <p>
          Service {health.data.status}, environment <strong>{health.data.environment}</strong>
        </p>
      )}
    </main>
  )
}
