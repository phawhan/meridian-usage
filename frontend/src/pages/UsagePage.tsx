import { useState } from 'react'

import type { Me } from '../api/types'
import { RefusalBanner } from '../components/RefusalBanner'
import { Select } from '../components/Select'
import { TopUsersTable } from '../components/TopUsersTable'
import { UsageTable } from '../components/UsageTable'
import { formatCompact, formatPeriod, formatUsd } from '../format'
import { useBreakdown, usePeriods, useTopUsers } from '../hooks/queries'

const VIEWS = [
  { value: 'platform', label: 'By platform' },
  { value: 'group,platform', label: 'By group and platform' },
  { value: 'week,platform', label: 'By week and platform' },
  { value: 'month,platform', label: 'By month and platform' },
  { value: 'platform,model', label: 'By model' },
  { value: 'platform,product', label: 'By product / agent' },
  { value: 'group,week', label: 'By group and week' },
]

export function UsagePage({ me }: { me: Me }) {
  const periods = usePeriods()
  const [period, setPeriod] = useState('last_30_days')
  const [group, setGroup] = useState('')
  const [view, setView] = useState('group,platform')

  const groupParam = group || undefined
  const byPlatform = useBreakdown(me.user_id, period, 'platform', groupParam)
  const breakdown = useBreakdown(me.user_id, period, view, groupParam)
  const topUsers = useTopUsers(me.user_id, period, groupParam)

  const groupOptions = [
    { value: '', label: me.readable_groups.length > 1 ? 'All groups I can see' : 'My group' },
    ...me.readable_groups.map((g) => ({ value: g, label: g })),
  ]

  return (
    <section>
      <div className="controls">
        <Select
          label="Period"
          value={period}
          onChange={setPeriod}
          options={(periods.data?.periods ?? [period]).map((p) => ({ value: p, label: formatPeriod(p) }))}
        />
        <Select label="Group" value={group} onChange={setGroup} options={groupOptions} />
        <Select label="View" value={view} onChange={setView} options={VIEWS} />
      </div>

      {byPlatform.error && <RefusalBanner error={byPlatform.error} />}
      {byPlatform.data && (
        <>
          {!byPlatform.data.period.complete && periods.data && (
            <p className="banner banner-note">
              Partial period: data covers {periods.data.data_from} to the day before{' '}
              {periods.data.data_to_exclusive}.
            </p>
          )}
          <div className="cards">
            <div className="card">
              <span className="muted">Total cost</span>
              <strong>{formatUsd(byPlatform.data.totals.cost_usd)}</strong>
            </div>
            <div className="card">
              <span className="muted">Total tokens</span>
              <strong>{formatCompact(byPlatform.data.totals.total_tokens)}</strong>
            </div>
            {byPlatform.data.rows.map((row) => (
              <div className="card" key={row.platform}>
                <span className="muted">{row.platform === 'claude' ? 'Claude' : 'Gemini'}</span>
                <strong>{formatUsd(row.cost_usd)}</strong>
                <span className="muted small">{formatCompact(row.total_tokens)} tokens</span>
              </div>
            ))}
          </div>
          <p className="muted small">Covering: {byPlatform.data.groups.join(', ')}</p>
        </>
      )}

      <h2>Breakdown</h2>
      {breakdown.error && !byPlatform.error && <RefusalBanner error={breakdown.error} />}
      {breakdown.data && <UsageTable data={breakdown.data} />}

      <h2>Top users</h2>
      {topUsers.error && !byPlatform.error && <RefusalBanner error={topUsers.error} />}
      {topUsers.data && <TopUsersTable users={topUsers.data} />}
    </section>
  )
}
