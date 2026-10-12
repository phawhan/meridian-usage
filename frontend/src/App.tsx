import { useState } from 'react'

import { RefusalBanner } from './components/RefusalBanner'
import { PersonaSwitcher } from './components/PersonaSwitcher'
import { useDirectory, useMe } from './hooks/queries'
import { usePersona } from './hooks/usePersona'
import { CapabilitiesPage } from './pages/CapabilitiesPage'
import { UsagePage } from './pages/UsagePage'

type Tab = 'usage' | 'capabilities'

export default function App() {
  const [persona, setPersona] = usePersona()
  const [tab, setTab] = useState<Tab>('usage')
  const directory = useDirectory()
  const me = useMe(persona)

  return (
    <>
      <header className="topbar">
        <div>
          <h1>Meridian AI usage</h1>
          {me.data && <span className={`env env-${me.data.environment}`}>{me.data.environment}</span>}
        </div>
        {directory.data && <PersonaSwitcher users={directory.data} value={persona} onChange={setPersona} />}
      </header>

      <main>
        {directory.error && <RefusalBanner error={directory.error} />}
        {!persona && <p className="banner banner-note">Choose a person to see what they can see.</p>}
        {me.error && <RefusalBanner error={me.error} />}

        {me.data && (
          <>
            <p className="whoami">
              <strong>{me.data.name}</strong> · {me.data.role.replace('_', ' ')} · {me.data.group_ids.join(', ')}
              <span className="muted">
                {' '}
                · scopes: {me.data.scopes.length ? me.data.scopes.join(', ') : 'none'}
              </span>
            </p>
            <nav className="tabs" aria-label="Sections">
              <button type="button" aria-current={tab === 'usage'} onClick={() => setTab('usage')}>
                Usage and cost
              </button>
              <button
                type="button"
                aria-current={tab === 'capabilities'}
                onClick={() => setTab('capabilities')}
              >
                Capability controls
              </button>
            </nav>
            {tab === 'usage' ? (
              <UsagePage key={persona} me={me.data} />
            ) : (
              <CapabilitiesPage key={persona} me={me.data} users={directory.data ?? []} />
            )}
          </>
        )}
      </main>
    </>
  )
}
