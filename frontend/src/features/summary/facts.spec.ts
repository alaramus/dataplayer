import { describe as suite, expect, it } from "vitest"

import type { NodeSummary } from "@/client"

import { describe } from "./facts"

function summary(over: Partial<NodeSummary> = {}): NodeSummary {
  return {
    node_id: "notes.txt",
    name: "notes.txt",
    kind: "file",
    representations: [{ kind: "text", title: "View as text" }],
    size_bytes: 2048,
    modified_at: "2026-09-02T10:00:00Z",
    permissions: "-rw-r--r--",
    ...over,
  }
}

function labelled(facts: { label: string; value: string }[], label: string) {
  return facts.find((fact) => fact.label === label)?.value
}

suite("describe", () => {
  it("states what every node has, in the source's own words", () => {
    const described = describe(summary())

    expect(labelled(described.facts, "Kind")).toBe("File")
    expect(labelled(described.facts, "Size")).toBe("2.0 KB")
    expect(labelled(described.facts, "Permissions")).toBe("-rw-r--r--")
    // The source wrote the title of the view; this screen only joins them.
    expect(labelled(described.facts, "Opens as")).toBe("View as text")
  })

  it("leaves out a time the platform did not state", () => {
    const described = describe(summary({ created_at: null, accessed_at: null }))

    expect(labelled(described.facts, "Created")).toBeUndefined()
    expect(labelled(described.facts, "Opened")).toBeUndefined()
    expect(labelled(described.facts, "Modified")).toBeDefined()
  })

  it("says so when a file has no viewer, rather than saying nothing", () => {
    const described = describe(summary({ name: "app.exe", representations: [] }))

    expect(labelled(described.facts, "Opens as")).toBe("Nothing this source can show")
  })

  it("does not ask a folder what it opens as", () => {
    const described = describe(
      summary({
        kind: "directory",
        representations: [],
        size_bytes: null,
        contents: { kind: "directory", entries: 3, files: 2, directories: 1 },
      })
    )

    expect(labelled(described.facts, "Opens as")).toBeUndefined()
    expect(labelled(described.contents, "Files")).toBe("2")
    expect(labelled(described.contents, "Folders")).toBe("1")
  })

  it("prints what a text file states about its lines", () => {
    const described = describe(
      summary({
        contents: {
          kind: "text",
          encoding: "utf-8-bom",
          lines: 120,
          longest_line_bytes: 4096,
          line_endings: "crlf",
        },
      })
    )

    expect(labelled(described.contents, "Encoding")).toBe("UTF-8 with a byte order mark")
    expect(labelled(described.contents, "Lines")).toBe("120")
    expect(labelled(described.contents, "Longest line")).toBe("4.0 KB")
    expect(labelled(described.contents, "Line endings")).toBe("CRLF (Windows)")
    expect(described.notice).toBeNull()
  })

  it("shows a count that hit a ceiling as absent with its reason", () => {
    const described = describe(
      summary({
        contents: {
          kind: "text",
          encoding: "utf-8",
          lines: null,
          not_counted: "This file is larger than 32 MB and was not read through",
        },
      })
    )

    // Absent, never a zero: a zero would read as a measurement.
    expect(labelled(described.contents, "Lines")).toBeUndefined()
    expect(described.notice).toContain("32 MB")
  })

  it("carries the source's refusal when the bytes are not the promised format", () => {
    const described = describe(
      summary({
        name: "forged.png",
        contents: null,
        notice: "This file is not a valid PNG or JPEG image",
        representations: [{ kind: "image", title: "View image" }],
      })
    )

    expect(described.contents).toEqual([])
    expect(described.notice).toBe("This file is not a valid PNG or JPEG image")
    // The facts that are still true survive the format that is not.
    expect(labelled(described.facts, "Size")).toBe("2.0 KB")
  })

  it("prints a dataset with the function that already prints one", () => {
    const described = describe(
      summary({
        name: "cities.parquet",
        contents: {
          kind: "parquet",
          rows: 3,
          row_groups: 1,
          columns: 2,
          compression: ["SNAPPY"],
          format_version: "2.6",
          size_bytes: 1024,
        },
      })
    )

    expect(labelled(described.contents, "Format")).toBe("Parquet 2.6")
    expect(labelled(described.contents, "Rows")).toBe("3")
  })

  it("counts an archive from what it declares", () => {
    const described = describe(
      summary({
        name: "bundle.zip",
        contents: {
          kind: "archive",
          entries: 4,
          files: 3,
          directories: 1,
          size_bytes: 4096,
          compressed_bytes: 1024,
          encrypted: 0,
          links: 0,
        },
      })
    )

    expect(labelled(described.contents, "Unpacked")).toBe("4.0 KB")
    expect(labelled(described.contents, "Packed")).toBe("1.0 KB")
    // Zero of either is not a fact worth a line.
    expect(labelled(described.contents, "Encrypted entries")).toBeUndefined()
    expect(labelled(described.contents, "Links")).toBeUndefined()
  })

  it("names a delimiter rather than printing the character", () => {
    const described = describe(
      summary({
        name: "people.tsv",
        contents: {
          kind: "delimited",
          delimiter: "tab",
          columns: 3,
          rows: 42,
          encoding: "utf-8",
        },
      })
    )

    expect(labelled(described.contents, "Separated by")).toBe("tab")
    expect(labelled(described.contents, "Rows")).toBe("42")
  })

  it("says what a recording states and leaves out what it does not", () => {
    const described = describe(
      summary({
        name: "clip.mp4",
        contents: {
          kind: "video",
          media_type: "video/mp4",
          duration_seconds: 125,
          width: 1920,
          height: 1080,
        },
      })
    )

    expect(labelled(described.contents, "Format")).toBe("MP4")
    expect(labelled(described.contents, "Duration")).toBe("2:05")
    expect(labelled(described.contents, "Size")).toBe("1920 × 1080")
  })

  it("shows an entry's own facts, which are the archive's", () => {
    const described = describe(
      summary({
        kind: "entry",
        name: "notes.txt",
        contents: { kind: "entry", compressed_bytes: 512, encrypted: false, link: false },
      })
    )

    expect(labelled(described.facts, "Kind")).toBe("Archive entry")
    expect(labelled(described.contents, "Packed")).toBe("512 B")
    expect(labelled(described.contents, "Encrypted")).toBeUndefined()
  })
})
