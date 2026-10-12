import type { AuditEntry } from '../api/types'
import { formatTimestamp } from '../format'

const onOff = (value: boolean | null) => (value === null ? '—' : value ? 'on' : 'off')

export function AuditList({ entries, nameOf }: { entries: AuditEntry[]; nameOf: (actor: string) => string }) {
  if (entries.length === 0) return <p className="muted">No changes yet.</p>
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Who</th>
            <th>Group</th>
            <th>Capability</th>
            <th>Change</th>
            <th className="num">Policy version</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e, i) => (
            <tr key={`${e.at}|${e.group}|${e.capability}|${i}`}>
              <td>{formatTimestamp(e.at)}</td>
              <td>{nameOf(e.by)}</td>
              <td>{e.group}</td>
              <td>{e.capability}</td>
              <td>
                {e.action === 'seed' ? `default: ${onOff(e.new_enabled)}` : `${onOff(e.old_enabled)} → ${onOff(e.new_enabled)}`}
                {e.action === 'reset' && <span className="muted"> (reset)</span>}
              </td>
              <td className="num">#{e.policy_file_id}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
