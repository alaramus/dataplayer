import type { LiveRows } from "./frames"

/**
 * What a market view holds, and how each batch of rows changes it (D323).
 *
 * The parts and their columns are the `market` representation's contract:
 * `ticker` (the symbol's day), `candles` (keyed by `open_time`), `order_book`
 * (`side`, `level`, `price`, `quantity`, `cumulative_quantity`) and `trades`.
 * They are the columns the grid shows for the same feeds, so a value reads
 * the same on both screens. Prices stay the source's decimal text; only what
 * a chart has to place is turned into a number.
 */

export interface Part {
  columns: string[]
  rows: (string | null)[][]
}

export type Parts = Record<string, Part>

// How many of each a view keeps; older ones fall off the end.
export const KEPT_TRADES = 200
export const KEPT_CANDLES = 1000

const KEPT: Record<string, number> = { trades: KEPT_TRADES, candles: KEPT_CANDLES }

function keyOf(row: (string | null)[], indexes: number[]): string {
  return JSON.stringify(indexes.map((index) => row[index] ?? null))
}

/** The parts after one batch: replaced, added to, or updated by key. */
export function applyRows(parts: Parts, batch: LiveRows): Parts {
  const before = parts[batch.part]
  const sameShape =
    before !== undefined &&
    before.columns.length === batch.columns.length &&
    before.columns.every((column, index) => column === batch.columns[index])
  let rows: (string | null)[][]
  if (batch.mode === "replace" || !sameShape) {
    rows = batch.rows
  } else if (batch.mode === "append") {
    rows = [...before.rows, ...batch.rows]
  } else {
    const indexes = batch.key.map((column) => batch.columns.indexOf(column)).filter((index) => index >= 0)
    const at = new Map(before.rows.map((row, index) => [keyOf(row, indexes), index]))
    rows = [...before.rows]
    for (const row of batch.rows) {
      const index = at.get(keyOf(row, indexes))
      if (index === undefined) {
        at.set(keyOf(row, indexes), rows.length)
        rows.push(row)
      } else {
        rows[index] = row
      }
    }
  }
  const kept = KEPT[batch.part]
  if (kept !== undefined && rows.length > kept) rows = rows.slice(rows.length - kept)
  return { ...parts, [batch.part]: { columns: batch.columns, rows } }
}

/** A part's rows as records by column name. */
export function records(part: Part | undefined): Record<string, string | null>[] {
  if (part === undefined) return []
  return part.rows.map((row) =>
    Object.fromEntries(part.columns.map((column, index) => [column, row[index] ?? null]))
  )
}

export interface Day {
  lastPrice: string | null
  change: string | null
  changePercent: string | null
  high: string | null
  low: string | null
  volume: string | null
  quoteVolume: string | null
}

export function dayOf(parts: Parts): Day | null {
  const [day] = records(parts.ticker)
  if (day === undefined) return null
  return {
    lastPrice: day.last_price ?? null,
    change: day.price_change ?? null,
    changePercent: day.price_change_percent ?? null,
    high: day.high_price ?? null,
    low: day.low_price ?? null,
    volume: day.volume ?? null,
    quoteVolume: day.quote_volume ?? null,
  }
}

/** Whether a signed decimal says the price went down. */
export function falling(change: string | null): boolean {
  return change !== null && change.trim().startsWith("-")
}

export interface ChartCandle {
  time: number
  open: number
  close: number
  low: number
  high: number
  volume: number
  closed: boolean
}

export function candlesOf(parts: Parts): ChartCandle[] {
  const found: ChartCandle[] = []
  for (const one of records(parts.candles)) {
    const time = Date.parse(one.open_time ?? "")
    const values = [one.open, one.close, one.low, one.high, one.volume].map((text) => Number(text ?? Number.NaN))
    if (Number.isNaN(time) || values.some((value) => Number.isNaN(value))) continue
    const [open, close, low, high, volume] = values as [number, number, number, number, number]
    found.push({ time, open, close, low, high, volume, closed: one.closed === "true" })
  }
  return found.sort((a, b) => a.time - b.time)
}

export interface Level {
  price: string
  quantity: string
  cumulative: string
  /** The cumulative quantity as a share of the deeper side's, 0 to 1. */
  depth: number
}

export interface Book {
  bids: Level[]
  asks: Level[]
}

export function bookOf(parts: Parts): Book {
  const all = records(parts.order_book)
  const deepest = Math.max(0, ...all.map((one) => Number(one.cumulative_quantity ?? 0) || 0))
  const side = (name: string): Level[] =>
    all
      .filter((one) => one.side === name)
      .sort((a, b) => Number(a.level) - Number(b.level))
      .map((one) => ({
        price: one.price ?? "",
        quantity: one.quantity ?? "",
        cumulative: one.cumulative_quantity ?? "",
        depth: deepest > 0 ? (Number(one.cumulative_quantity ?? 0) || 0) / deepest : 0,
      }))
  return { bids: side("bid"), asks: side("ask") }
}

export interface Trade {
  id: string
  price: string
  quantity: string
  time: string
  /** Taken by a seller: the buyer's order was resting in the book. */
  sold: boolean
}

/** The newest trades first. */
export function tradesOf(parts: Parts): Trade[] {
  return records(parts.trades)
    .map((one) => ({
      id: one.id ?? "",
      price: one.price ?? "",
      quantity: one.quantity ?? "",
      time: one.time ?? "",
      sold: one.buyer_is_maker === "true",
    }))
    .reverse()
}

/**
 * A decimal as a person reads it: Binance pads to eight places, and
 * `74144.64000000` says nothing `74144.64` does not. Nothing is rounded.
 */
export function shown(text: string | null): string {
  if (text === null || text === "") return "—"
  if (!text.includes(".")) return text
  const trimmed = text.replace(/0+$/, "")
  return trimmed.endsWith(".") ? trimmed.slice(0, -1) : trimmed
}
