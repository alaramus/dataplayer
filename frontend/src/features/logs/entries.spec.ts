import { describe, expect, it } from "vitest"

import type { LogEntry } from "@/client"

import { statusOf, textOf, toneOf } from "./entries"

function entry(overrides: Partial<LogEntry> = {}): LogEntry {
  return {
    time: "2026-09-28T12:00:00.123000+00:00",
    process: "backend",
    level: "INFO",
    logger: "app.test",
    message: "Something happened",
    ...overrides,
  }
}

const access = (status: number) =>
  entry({ logger: "uvicorn.access", message: `172.18.0.1:1 - "GET /api/v1/jobs/ HTTP/1.1" ${String(status)}` })

describe("a log entry", () => {
  it("is red when it failed and amber when it warned", () => {
    expect(toneOf(entry({ level: "ERROR" }))).toBe("error")
    expect(toneOf(entry({ level: "WARNING" }))).toBe("warning")
    expect(toneOf(entry())).toBeNull()
  })

  it("is coloured by the answer when it is a request, whatever its level", () => {
    expect(statusOf(access(502))).toBe(502)
    expect(toneOf(access(502))).toBe("error")
    expect(toneOf(access(404))).toBe("warning")
    expect(toneOf(access(200))).toBeNull()
    expect(statusOf(entry({ message: 'said "x" 500' }))).toBeNull()
  })

  it("copies as text with everything it holds", () => {
    const text = textOf(entry({
      level: "ERROR",
      ref: "K7Q3PD",
      request: "GET /api/v1/connectors/",
      exception: "Traceback …",
    }))

    expect(text).toContain("ERROR backend app.test")
    expect(text).toContain("Request: GET /api/v1/connectors/")
    expect(text).toContain("Ref: K7Q3PD")
    expect(text).toContain("Traceback …")
  })
})
