import { describe, expect, it } from "vitest"

import { openingFrame, readServerFrame } from "./frames"
import type { LiveRows } from "./frames"
import { KEPT_TRADES, applyRows, bookOf, candlesOf, dayOf, falling, shown, tradesOf } from "./model"
import type { Parts } from "./model"
import { openWatchLink } from "./watchLink"
import type { WatchSocketLike, WatchState } from "./watchLink"

const CANDLE_COLUMNS = ["open_time", "close_time", "open", "high", "low", "close", "volume", "closed"]

function rows(part: string, mode: LiveRows["mode"], columns: string[], data: (string | null)[][], key: string[] = []): LiveRows {
  return { part, mode, columns, rows: data, key }
}

describe("the rows a watch is told", () => {
  it("replaces a part, adds to it, and updates a row by its key", () => {
    let parts: Parts = {}
    parts = applyRows(parts, rows("candles", "replace", CANDLE_COLUMNS, [
      ["2026-11-09T06:40:00.000Z", null, "1", "2", "0.5", "1.5", "10", "true"],
      ["2026-11-09T06:41:00.000Z", null, "1.5", "2", "1", "1.8", "4", "false"],
    ], ["open_time"]))
    parts = applyRows(parts, rows("candles", "upsert", CANDLE_COLUMNS, [
      ["2026-11-09T06:41:00.000Z", null, "1.5", "2.5", "1", "2.4", "6", "true"],
      ["2026-11-09T06:42:00.000Z", null, "2.4", "2.4", "2.4", "2.4", "0", "false"],
    ], ["open_time"]))

    const candles = candlesOf(parts)
    expect(candles.map((one) => one.close)).toEqual([1.5, 2.4, 2.4])
    expect(candles[1]?.high).toBe(2.5)
    expect(candles[1]?.closed).toBe(true)
  })

  it("keeps only the newest trades, and says the newest first", () => {
    const columns = ["id", "price", "quantity", "time", "buyer_is_maker"]
    let parts: Parts = {}
    const many = Array.from({ length: KEPT_TRADES + 5 }, (_, index) => [String(index), "1", "1", "", "false"])
    parts = applyRows(parts, rows("trades", "replace", columns, many))
    parts = applyRows(parts, rows("trades", "append", columns, [["9999", "2", "1", "", "true"]]))

    const trades = tradesOf(parts)
    expect(trades).toHaveLength(KEPT_TRADES)
    expect(trades[0]).toMatchObject({ id: "9999", sold: true })
  })

  it("lays the book out by side, best first, each level's depth a share of the deepest", () => {
    const columns = ["side", "level", "price", "quantity", "cumulative_quantity"]
    const parts = applyRows({}, rows("order_book", "replace", columns, [
      ["bid", "2", "99", "3", "4"],
      ["bid", "1", "100", "1", "1"],
      ["ask", "1", "101", "2", "2"],
    ]))

    const book = bookOf(parts)
    expect(book.bids.map((one) => one.price)).toEqual(["100", "99"])
    expect(book.bids[1]?.depth).toBe(1)
    expect(book.asks[0]?.depth).toBe(0.5)
  })

  it("reads the day, and whether it went down", () => {
    const parts = applyRows({}, rows("ticker", "replace", ["last_price", "price_change", "price_change_percent"], [
      ["74144.64000000", "-1681.36000000", "-2.217"],
    ]))

    expect(dayOf(parts)?.lastPrice).toBe("74144.64000000")
    expect(falling(dayOf(parts)?.change ?? null)).toBe(true)
    expect(falling("12.5")).toBe(false)
  })

  it("shows a decimal without Binance's padding and without rounding", () => {
    expect(shown("74144.64000000")).toBe("74144.64")
    expect(shown("100.00000000")).toBe("100")
    expect(shown("0.00001000")).toBe("0.00001")
    expect(shown("1500")).toBe("1500")
    expect(shown(null)).toBe("—")
  })
})

describe("the frames of a watch", () => {
  it("opens with who is asking and what is watched", () => {
    expect(JSON.parse(openingFrame("tok", "c1", "spot:symbol:BTCUSDT:market", "5m"))).toEqual({
      type: "open",
      token: "tok",
      connector_id: "c1",
      node_id: "spot:symbol:BTCUSDT:market",
      interval: "5m",
    })
  })

  it("reads what it knows and refuses what it does not", () => {
    expect(readServerFrame('{"type":"ready","intervals":["1m"],"interval":"1m"}')).toEqual({
      type: "ready",
      intervals: ["1m"],
      interval: "1m",
    })
    expect(readServerFrame('{"type":"rows","part":"trades","mode":"append","columns":["id"],"rows":[["1"]],"key":[]}'))
      .toMatchObject({ type: "rows", part: "trades", rows: [["1"]] })
    expect(readServerFrame('{"type":"rows","part":"trades","mode":"sideways","columns":[],"rows":[]}')).toBeNull()
    expect(readServerFrame('{"type":"rows","part":"trades","mode":"append","columns":[],"rows":[[1]]}')).toBeNull()
    expect(readServerFrame("not json")).toBeNull()
  })
})

class FakeSocket implements WatchSocketLike {
  sent: string[] = []
  closed = false
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  send(data: string) {
    this.sent.push(data)
  }
  close() {
    this.closed = true
  }
  say(frame: object) {
    this.onmessage?.({ data: JSON.stringify(frame) } as MessageEvent)
  }
}

describe("a watch's socket", () => {
  function opened() {
    const sockets: FakeSocket[] = []
    const states: WatchState[] = []
    const got: LiveRows[] = []
    const scheduled: { run: () => void; ms: number }[] = []
    const link = openWatchLink({
      url: "ws://x",
      token: "tok",
      connectorId: "c1",
      nodeId: "n",
      interval: null,
      onRows: (one) => got.push(one),
      onState: (one) => states.push(one),
      open: () => {
        const socket = new FakeSocket()
        sockets.push(socket)
        return socket
      },
      later: (run, ms) => scheduled.push({ run, ms }),
      cancelLater: () => undefined,
    })
    return { link, sockets, states, got, scheduled }
  }

  it("says what it watches once open, then hands on the rows", () => {
    const { sockets, states, got } = opened()
    const socket = sockets[0]!
    socket.onopen?.(new Event("open"))
    socket.say({ type: "ready", intervals: ["1m", "5m"], interval: "1m" })
    socket.say({ type: "rows", part: "trades", mode: "append", columns: ["id"], rows: [["1"]], key: [] })

    expect(JSON.parse(socket.sent[0]!)).toMatchObject({ type: "open", node_id: "n" })
    expect(states.at(-1)).toEqual({ kind: "open", intervals: ["1m", "5m"], interval: "1m" })
    expect(got).toHaveLength(1)
  })

  it("opens again after a drop, but not after a refusal", () => {
    const { sockets, states, scheduled } = opened()
    sockets[0]!.onclose?.(new CloseEvent("close"))
    expect(states.at(-1)).toEqual({ kind: "lost", retryInMs: 1000 })
    scheduled[0]!.run()
    expect(sockets).toHaveLength(2)

    sockets[1]!.say({ type: "refused", code: "not_found", message: "No such node", error_kind: null })
    sockets[1]!.onclose?.(new CloseEvent("close"))
    expect(states.at(-1)).toEqual({ kind: "refused", code: "not_found", message: "No such node" })
    expect(scheduled).toHaveLength(1)
  })

  it("lets go of its socket when closed here", () => {
    const { link, sockets, states } = opened()
    link.close()
    sockets[0]!.onclose?.(new CloseEvent("close"))

    expect(sockets[0]!.closed).toBe(true)
    expect(states.at(-1)).toEqual({ kind: "connecting" })
  })
})
