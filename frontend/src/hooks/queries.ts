import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type {
  AuditEntry,
  Breakdown,
  Capability,
  CapabilityStatus,
  DirectoryEntry,
  Me,
  Periods,
  TopUser,
} from '../api/types'

// Every query key includes the persona: switching person never shows the previous
// person's cached data.

export const useDirectory = () =>
  useQuery({ queryKey: ['directory'], queryFn: () => api<DirectoryEntry[]>('/directory/users', null) })

export const usePeriods = () =>
  useQuery({ queryKey: ['periods'], queryFn: () => api<Periods>('/periods', null) })

export const useMe = (persona: string | null) =>
  useQuery({
    queryKey: ['me', persona],
    queryFn: () => api<Me>('/me', persona),
    enabled: persona !== null,
  })

export const useBreakdown = (persona: string, period: string, by: string, group?: string) =>
  useQuery({
    queryKey: ['breakdown', persona, period, by, group],
    queryFn: () => api<Breakdown>('/usage/breakdown', persona, { params: { period, by, group } }),
  })

export const useTopUsers = (persona: string, period: string, group?: string) =>
  useQuery({
    queryKey: ['top-users', persona, period, group],
    queryFn: () => api<TopUser[]>('/usage/top-users', persona, { params: { period, group, limit: 10 } }),
  })

export const useCapabilities = (persona: string) =>
  useQuery({
    queryKey: ['capabilities', persona],
    queryFn: () => api<CapabilityStatus[]>('/capabilities', persona),
  })

export const useAudit = (persona: string) =>
  useQuery({
    queryKey: ['audit', persona],
    queryFn: () => api<AuditEntry[]>('/capabilities/audit', persona, { params: { limit: 50 } }),
  })

type Change = { group: string; capability: Capability; enabled: boolean | null }

/** enabled null = reset to the environment baseline. */
export function useChangeCapability(persona: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ group, capability, enabled }: Change) =>
      enabled === null
        ? api<CapabilityStatus>(`/capabilities/${group}/${capability}/reset`, persona, { method: 'POST' })
        : api<CapabilityStatus>(`/capabilities/${group}/${capability}`, persona, {
            method: 'PUT',
            body: { enabled },
          }),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ['capabilities'] })
      void client.invalidateQueries({ queryKey: ['audit'] })
    },
  })
}
