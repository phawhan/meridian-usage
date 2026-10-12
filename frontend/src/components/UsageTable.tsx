import type { Breakdown, Dimension } from '../api/types'
import { formatTokens, formatUsd } from '../format'

const HEADINGS: Record<Dimension, string> = {
  platform: 'Platform',
  group: 'Group',
  week: 'Week',
  month: 'Month',
  model: 'Model',
  product: 'Product / agent',
}

export function UsageTable({ data }: { data: Breakdown }) {
  if (data.rows.length === 0) return <p className="muted">No usage in this period.</p>
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {data.by.map((d) => (
              <th key={d}>{HEADINGS[d]}</th>
            ))}
            <th className="num">Requests</th>
            <th className="num">Input tokens</th>
            <th className="num">Output tokens</th>
            <th className="num">Total tokens</th>
            <th className="num">Cost</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row) => (
            <tr key={data.by.map((d) => row[d]).join('|')}>
              {data.by.map((d) => (
                <td key={d}>{row[d]}</td>
              ))}
              <td className="num">{row.requests === null ? '—' : formatTokens(row.requests)}</td>
              <td className="num">{formatTokens(row.input_tokens)}</td>
              <td className="num">{formatTokens(row.output_tokens)}</td>
              <td className="num">{formatTokens(row.total_tokens)}</td>
              <td className="num">{formatUsd(row.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th colSpan={data.by.length + 3}>Total</th>
            <th className="num">{formatTokens(data.totals.total_tokens)}</th>
            <th className="num">{formatUsd(data.totals.cost_usd)}</th>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}
