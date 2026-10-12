import { useCallback, useState } from 'react'

const KEY = 'meridian.persona'

function read(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null // storage blocked (private window etc.): fall back to choosing again
  }
}

/** The simulated identity, remembered per browser for convenience only. */
export function usePersona(): [string | null, (userId: string | null) => void] {
  const [persona, setPersona] = useState<string | null>(read)

  const choose = useCallback((userId: string | null) => {
    setPersona(userId)
    try {
      if (userId) localStorage.setItem(KEY, userId)
      else localStorage.removeItem(KEY)
    } catch {
      // not remembered; still works for this session
    }
  }, [])

  return [persona, choose]
}
