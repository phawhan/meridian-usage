// Mirrors backend/app/models/api.py and app/api/routes/{me,meta}.py. Hand-written: the API
// is small; generating from OpenAPI would be the next step if it grows.

export type Platform = 'claude' | 'gemini'
export type Dimension = 'platform' | 'group' | 'week' | 'month' | 'model' | 'product'
export type Capability = 'usage-connector' | 'web-search' | 'code-execution'

export type DirectoryEntry = {
  user_id: string
  name: string
  role: 'member' | 'team_lead' | 'platform_admin'
  group_ids: string[]
}

export type Me = {
  user_id: string
  name: string
  email: string
  role: DirectoryEntry['role']
  group_ids: string[]
  environment: 'dev' | 'staging' | 'prod'
  scopes: string[]
  readable_groups: string[]
  writable_groups: string[]
}

export type Periods = {
  data_from: string
  data_to_exclusive: string
  periods: string[]
}

export type PeriodOut = {
  label: string
  start: string
  end_exclusive: string
  complete: boolean
}

export type Totals = { total_tokens: number; cost_usd: number }

export type BreakdownRow = Partial<Record<Dimension, string>> & {
  requests: number | null
  input_tokens: number
  output_tokens: number
  total_tokens: number
  cost_usd: number
}

export type Breakdown = {
  period: PeriodOut
  groups: string[]
  by: Dimension[]
  rows: BreakdownRow[]
  totals: Totals
}

export type TopUser = {
  user_id: string
  name: string
  email: string
  group: string
  total_tokens: number
  cost_usd: number
}

export type CapabilityStatus = {
  group: string
  capability: Capability
  enabled: boolean
  baseline: boolean
  drift: boolean
  updated_at: string | null
  updated_by: string | null
}

export type AuditEntry = {
  group: string
  capability: Capability
  action: 'seed' | 'set' | 'reset'
  old_enabled: boolean | null
  new_enabled: boolean
  policy_file_id: number
  at: string
  by: string
}

// contracts/tools.schema.json Denial, and the 401 body.
export type Refusal =
  | { error: 'permission_denied'; reason: string; required_scope?: string }
  | { error: 'unauthenticated'; reason: string }
