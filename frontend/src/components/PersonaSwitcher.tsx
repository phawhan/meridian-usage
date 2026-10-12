import type { DirectoryEntry } from '../api/types'

const ROLE = { member: 'member', team_lead: 'team lead', platform_admin: 'platform admin' } as const

type Props = {
  users: DirectoryEntry[]
  value: string | null
  onChange: (userId: string | null) => void
}

/** Simulated sign-in: pick who you are. The server applies that person's permissions. */
export function PersonaSwitcher({ users, value, onChange }: Props) {
  const byGroup = new Map<string, DirectoryEntry[]>()
  for (const user of users) {
    const group = user.group_ids[0] ?? 'no group'
    byGroup.set(group, [...(byGroup.get(group) ?? []), user])
  }
  const rank = (u: DirectoryEntry) => ['platform_admin', 'team_lead', 'member'].indexOf(u.role)

  return (
    <label className="field">
      <span>Signed in as (simulated)</span>
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">Choose a person…</option>
        {[...byGroup.entries()]
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([group, members]) => (
            <optgroup key={group} label={group}>
              {members
                .sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name))
                .map((u) => (
                  <option key={u.user_id} value={u.user_id}>
                    {u.name} ({ROLE[u.role]})
                  </option>
                ))}
            </optgroup>
          ))}
      </select>
    </label>
  )
}
