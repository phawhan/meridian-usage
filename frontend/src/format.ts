const tokens = new Intl.NumberFormat('en-US')
const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })
const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export const formatTokens = (n: number) => tokens.format(n)
export const formatCompact = (n: number) => compact.format(n)
export const formatUsd = (n: number) => usd.format(n)

export function formatPeriod(label: string): string {
  if (label === 'last_7_days') return 'Last 7 days'
  if (label === 'last_30_days') return 'Last 30 days'
  if (/^\d{4}-W\d{2}$/.test(label)) return `Week ${label}`
  const [year, month] = label.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, 1)).toLocaleString('en-US', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

export const formatTimestamp = (iso: string) =>
  new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }) + ' UTC'
