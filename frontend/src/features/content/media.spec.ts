import { describe, expect, it } from "vitest"

import { formatDuration, mediaDetails } from "./media"
import { pageScale } from "./pdfScale"

describe("mediaDetails", () => {
  it("says what the container proved about a sound file", () => {
    expect(
      mediaDetails({
        kind: "audio",
        filename: "tone.wav",
        media_type: "audio/wav",
        size_bytes: 32044,
        duration_seconds: 2,
        channels: 1,
        sample_rate: 8000,
      })
    ).toBe("WAV · mono · 8 kHz · 0:02 · 31.3 KB")
  })

  it("leaves out what the container did not state", () => {
    expect(
      mediaDetails({
        kind: "audio",
        filename: "voice.mp3",
        media_type: "audio/mpeg",
        size_bytes: 1024,
        duration_seconds: null,
        channels: null,
        sample_rate: null,
      })
    ).toBe("MP3 · 1.0 KB")
  })

  it("gives a recording its picture size", () => {
    expect(
      mediaDetails({
        kind: "video",
        filename: "clip.mp4",
        media_type: "video/mp4",
        size_bytes: 1791,
        duration_seconds: 2,
        width: 160,
        height: 120,
      })
    ).toBe("MP4 · 160 × 120 · 0:02 · 1.7 KB")
  })
})

describe("formatDuration", () => {
  it("counts minutes and seconds, and hours only when there are any", () => {
    expect(formatDuration(9)).toBe("0:09")
    expect(formatDuration(75)).toBe("1:15")
    expect(formatDuration(3725)).toBe("1:02:05")
  })
})

describe("pageScale", () => {
  it("fits the page to the room there is, edge to edge", () => {
    expect(pageScale(607, 595)).toBeCloseTo(1)
  })

  it("does not shrink a page to nothing before the panel is laid out", () => {
    expect(pageScale(0, 595)).toBe(1)
    expect(pageScale(643, 0)).toBe(1)
  })

  it("stops enlarging a small page past a readable size", () => {
    expect(pageScale(4000, 200)).toBe(3)
  })
})
