import type { TopUser } from '../api/types'
import { formatTokens, formatUsd } from '../format'

export function TopUsersTable({ users }: { users: TopUser[] }) {
  if (users.length === 0) return <p className="muted">No usage in this period.</p>
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th className="num">#</th>
            <th>Name</th>
            <th>Group</th>
            <th className="num">Total tokens</th>
            <th className="num">Cost</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u, i) => (
            <tr key={`${u.user_id}|${u.group}`}>
              <td className="num">{i + 1}</td>
              <td>
                {u.name} <span className="muted">{u.email}</span>
              </td>
              <td>{u.group}</td>
              <td className="num">{formatTokens(u.total_tokens)}</td>
              <td className="num">{formatUsd(u.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
