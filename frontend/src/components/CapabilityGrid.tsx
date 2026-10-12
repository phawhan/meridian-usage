import type { Capability, CapabilityStatus } from '../api/types'

const CAPABILITIES: Capability[] = ['usage-connector', 'web-search', 'code-execution']

type Props = {
  states: CapabilityStatus[]
  writableGroups: string[]
  nameOf: (actor: string | null) => string
  busy: boolean
  onChange: (group: string, capability: Capability, enabled: boolean | null) => void
}

/** Group x capability switches. Disabled toggles are a hint only; the server decides. */
export function CapabilityGrid({ states, writableGroups, nameOf, busy, onChange }: Props) {
  const groups = [...new Set(states.map((s) => s.group))].sort()
  const find = (g: string, c: Capability) => states.find((s) => s.group === g && s.capability === c)

  return (
    <div className="table-wrap">
      <table className="grid">
        <thead>
          <tr>
            <th>Group</th>
            {CAPABILITIES.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => {
            const canWrite = writableGroups.includes(group)
            return (
              <tr key={group}>
                <th scope="row">{group}</th>
                {CAPABILITIES.map((capability) => {
                  const state = find(group, capability)
                  if (!state) return <td key={capability}>—</td>
                  return (
                    <td key={capability}>
                      <label className="toggle">
                        <input
                          type="checkbox"
                          checked={state.enabled}
                          disabled={!canWrite || busy}
                          onChange={(e) => onChange(group, capability, e.target.checked)}
                        />
                        <span>{state.enabled ? 'On' : 'Off'}</span>
                      </label>
                      {state.drift && (
                        <span className="badge" title="Differs from this environment's default">
                          changed from default ({state.baseline ? 'on' : 'off'})
                        </span>
                      )}
                      <div className="muted small">
                        {nameOf(state.updated_by)}
                        {state.drift && canWrite && (
                          <button
                            type="button"
                            className="link"
                            disabled={busy}
                            onClick={() => onChange(group, capability, null)}
                          >
                            reset
                          </button>
                        )}
                      </div>
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
