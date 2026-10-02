import { describe, expect, it } from "vitest"

import { linesOf, parseLine } from "./stream"
import type { SearchLine } from "./stream"

function body(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

async function read(stream: ReadableStream<Uint8Array>): Promise<SearchLine[]> {
  const lines: SearchLine[] = []
  for await (const line of linesOf(stream)) lines.push(line)
  return lines
}

const END = { type: "end", nothing_found: false, asked: 1, superseded: false }

describe("reading the search's stream", () => {
  it("reads a line however its bytes were split", async () => {
    const text = JSON.stringify(END)

    const lines = await read(body(text.slice(0, 5), text.slice(5), "\n"))

    expect(lines).toEqual([END])
  })

  it("reads several lines from one chunk, and the last without its newline", async () => {
    const best = { type: "best", hits: [] }

    const lines = await read(body(`${JSON.stringify(best)}\n${JSON.stringify(END)}`))

    expect(lines.map((line) => line.type)).toEqual(["best", "end"])
  })

  it("keeps a character whose bytes arrive in two chunks", async () => {
    const encoder = new TextEncoder()
    const bytes = encoder.encode(`${JSON.stringify({ type: "best", hits: [], note: "é" })}\n`)
    const split = bytes.indexOf(0xc3) + 1
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, split))
        controller.enqueue(bytes.slice(split))
        controller.close()
      },
    })

    const [line] = await read(stream)

    expect(line).toMatchObject({ note: "é" })
  })

  it("drops a line of a type it does not know rather than half reading it", () => {
    expect(parseLine(JSON.stringify({ type: "mystery" }))).toBeNull()
    expect(parseLine("not json")).toBeNull()
    expect(parseLine(JSON.stringify(END))).toEqual(END)
  })
})
