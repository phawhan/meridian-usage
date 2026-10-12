import type { DirectoryEntry, Me } from '../api/types'
import { AuditList } from '../components/AuditList'
import { CapabilityGrid } from '../components/CapabilityGrid'
import { RefusalBanner } from '../components/RefusalBanner'
import { useAudit, useCapabilities, useChangeCapability } from '../hooks/queries'

export function CapabilitiesPage({ me, users }: { me: Me; users: DirectoryEntry[] }) {
  const states = useCapabilities(me.user_id)
  const audit = useAudit(me.user_id)
  const change = useChangeCapability(me.user_id)

  const names = new Map(users.map((u) => [u.user_id, u.name]))
  const nameOf = (actor: string | null) =>
    actor === null ? '' : actor.startsWith('system:') ? 'Environment default' : (names.get(actor) ?? actor)

  return (
    <section>
      <p className="muted">
        {me.writable_groups.length === 0
          ? `You can view these switches but not change them in ${me.environment}.`
          : me.writable_groups.length === me.readable_groups.length
            ? 'You can change switches for every group shown.'
            : `You can change switches for: ${me.writable_groups.join(', ')}.`}
      </p>
      {change.error && <RefusalBanner error={change.error} />}
      {states.error && <RefusalBanner error={states.error} />}
      {states.data && (
        <CapabilityGrid
          states={states.data}
          writableGroups={me.writable_groups}
          nameOf={nameOf}
          busy={change.isPending}
          onChange={(group, capability, enabled) => change.mutate({ group, capability, enabled })}
        />
      )}

      <h2>Change history</h2>
      {audit.data && <AuditList entries={audit.data} nameOf={nameOf} />}
    </section>
  )
}
