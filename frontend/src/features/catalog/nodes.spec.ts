import { describe, expect, it } from "vitest"

import { at, first } from "@/shared/testing/collections"
import bundledIcons from "@quasar/extras/material-symbols-outlined/icons.json"

import {
  ICONS,
  MATERIALIZED_VIEW_ICON,
  REPORT_SECTION_ICON,
  TIMESCALE_ICON,
  groupTitle,
  groupsOf,
  levelPath,
  roleOf,
  showsPath,
  toListNodes,
} from "./nodes"
import type { CatalogNode } from "./nodes"

function group(id: string) {
  return first(
    toListNodes([{ kind: "schema", id, name: id, has_children: true, representations: [] }])
  )
}

const leaf = (kind: "table" | "view" | "file" | "dataset", hasChildren = false) =>
  kind === "file"
    ? ({
        kind,
        id: "a",
        name: "a",
        has_children: hasChildren,
        size_bytes: 1,
        representations: [],
      } as CatalogNode)
    : ({
        kind,
        id: "a",
        name: "a",
        has_children: hasChildren,
        representations: [],
      } as CatalogNode)

describe("what the catalog does with a node", () => {
  it("puts a schema in the filter rather than in the list", () => {
    expect(
      roleOf({ kind: "schema", id: "public", name: "public", has_children: true, representations: [] })
    ).toBe("group")
  })

  it("walks into a directory, empty or not", () => {
    expect(
      roleOf({ kind: "directory", id: "d", name: "d", has_children: false, representations: [] })
    ).toBe("container")
  })

  it("opens a table, a view and a file", () => {
    expect(roleOf(leaf("table"))).toBe("leaf")
    expect(roleOf(leaf("view"))).toBe("leaf")
    expect(roleOf(leaf("file"))).toBe("leaf")
    expect(roleOf(leaf("dataset"))).toBe("leaf")
  })

  it("walks into a file that says it holds nodes and nothing else", () => {
    // An archive: what is inside it has the viewers, and the file itself has
    // none of its own.
    expect(roleOf(leaf("file", true))).toBe("container")
  })

  it("opens a file that holds nodes and also says how it opens", () => {
    // A workbook does both. Walking into a spreadsheet before a single figure
    // can be seen is a file behaving like a directory because of how it is
    // built rather than because of what it is (D51).
    const workbook = {
      kind: "file",
      id: "budget.xlsx",
      name: "budget.xlsx",
      has_children: true,
      size_bytes: 1,
      representations: [{ kind: "table", title: "View as table" }],
    } as CatalogNode

    expect(roleOf(workbook)).toBe("leaf")
    // And it is drawn as what opening it shows, not as a folder.
    expect(first(toListNodes([workbook])).icon).toBe("grid_on")
  })

  it("names the grouping a node was listed under, when it was", () => {
    const mapped = first(
      toListNodes(
        [
          {
            kind: "table",
            id: "sales.orders",
            name: "orders",
            has_children: true,
            representations: [{ kind: "table", title: "View as table" }],
          },
        ],
        "sales"
      )
    )

    expect(mapped.group).toBe("sales")
  })

  it("leaves the grouping out when a level was listed on its own", () => {
    const mapped = first(
      toListNodes([
        {
          kind: "table",
          id: "t",
          name: "t",
          has_children: true,
          representations: [{ kind: "table", title: "View as table" }],
        },
      ])
    )

    expect(mapped.group).toBeUndefined()
  })
})

describe("a key-value database", () => {
  const db = (index: number, keys: number | null, preferred = false) =>
    ({
      kind: "database" as const,
      id: `d${String(index)}`,
      name: `db${String(index)}`,
      has_children: true,
      preferred,
      keys,
      representations: [],
    })

  it("is a grouping, like a schema and unlike a folder", () => {
    // Which is the whole of D91's "the number in the connection says where to
    // start, not where to stay": a grouping is switched in the head of the
    // panel, a folder is walked into.
    expect(roleOf(db(0, 0))).toBe("group")
  })

  it("says how full it is, and says so when it is empty", () => {
    expect(first(toListNodes([db(0, 110)])).caption).toBe("110 keys")
    expect(first(toListNodes([db(1, 1)])).caption).toBe("1 key")
    expect(first(toListNodes([db(2, 0)])).caption).toBe("empty")
    expect(first(toListNodes([db(3, null)])).caption).toBeUndefined()
  })

  it("carries the source's word for which one to open on", () => {
    const [plain, named] = toListNodes([db(0, 0), db(3, 2, true)])

    expect(plain?.preferred).toBe(false)
    expect(named?.preferred).toBe(true)
  })

  it("is called a database above the control that picks one", () => {
    // The word comes off the kind, never off the type of the source:
    // "Schemas" over a list of Redis databases would be one word with two
    // meanings.
    expect(groupTitle(toListNodes([db(0, 0)]))).toBe("Databases")
    expect(groupTitle([group("public")])).toBe("Schemas")
    expect(groupTitle([])).toBe("Groups")
  })
})

describe("groupsOf", () => {
  it("offers the schemas of a level and nothing else", () => {
    const nodes = toListNodes([
      { kind: "schema", id: "public", name: "public", has_children: true, representations: [] },
      {
        kind: "table",
        id: "t",
        name: "t",
        has_children: true,
        representations: [{ kind: "table", title: "View as table" }],
      },
    ])

    expect(groupsOf(nodes).map((node) => node.id)).toEqual(["public"])
  })

  it("marks a system schema so it is not the one selected by default", () => {
    const nodes = toListNodes([
      {
        kind: "schema",
        id: "pg_catalog",
        name: "pg_catalog",
        has_children: true,
        is_system: true,
        representations: [],
      },
      { kind: "schema", id: "public", name: "public", has_children: true, representations: [] },
    ])

    expect(at(nodes, 0).system).toBe(true)
    expect(at(nodes, 1).system).toBe(false)
  })
})

describe("toListNodes", () => {
  it("offers structure where the source says the node has one", () => {
    expect(
      first(
        toListNodes([
          {
            kind: "table",
            id: "public.orders",
            name: "orders",
            has_children: false,
            describable: true,
            representations: [{ kind: "table", title: "View as table" }],
          },
        ])
      ).describable
    ).toBe(true)
    expect(
      first(
        toListNodes([
          {
            kind: "file",
            id: "a.csv",
            name: "a.csv",
            has_children: false,
            size_bytes: 1,
            representations: [{ kind: "table", title: "View as table" }],
          },
        ])
      ).describable
    ).toBe(false)
    expect(
      first(
        toListNodes([
          {
            kind: "dataset",
            id: "b.xlsx/1",
            name: "Revenue",
            has_children: false,
            describable: true,
            representations: [{ kind: "table", title: "View as table" }],
          },
        ])
      ).describable
    ).toBe(true)
  })

  it("says what a sheet holds before it is opened", () => {
    const node = first(
      toListNodes([
        {
          kind: "dataset",
          id: "b.xlsx/1",
          name: "Revenue",
          has_children: false,
          row_count: 120,
          column_count: 3,
          representations: [{ kind: "table", title: "View as table" }],
        },
      ])
    )

    expect(node.caption).toBe("120 rows · 3 columns")
    expect(node.icon).toBe("grid_on")
  })

  it("counts one row as one, and says when a sheet is hidden", () => {
    const node = first(
      toListNodes([
        {
          kind: "dataset",
          id: "b.xlsx/3",
          name: "Working notes",
          has_children: false,
          row_count: 1,
          column_count: 1,
          hidden: true,
          representations: [{ kind: "table", title: "View as table" }],
        },
      ])
    )

    expect(node.caption).toBe("1 row · 1 column · hidden")
  })

  it("draws an entry of an archive by what opening it shows", () => {
    const [file, folder, link] = toListNodes([
      {
        kind: "entry",
        id: "bundle.zip/readme.md",
        name: "readme.md",
        has_children: false,
        size_bytes: 2048,
        representations: [{ kind: "markdown", title: "View as document" }],
      },
      {
        kind: "entry",
        id: "bundle.zip/docs",
        name: "docs",
        has_children: true,
        representations: [],
      },
      {
        kind: "entry",
        id: "bundle.zip/elsewhere",
        name: "elsewhere",
        has_children: false,
        is_link: true,
        representations: [],
      },
    ])

    expect(file?.icon).toBe("article")
    expect(file?.caption).toBe("2.0 KB")
    expect(file?.role).toBe("leaf")
    expect(folder?.icon).toBe("folder_open")
    expect(folder?.role).toBe("container")
    expect(link?.caption).toBe("link")
  })

  it("draws a workbook as a place, since that is what it is", () => {
    const node = first(
      toListNodes([
        {
          kind: "file",
          id: "b.xlsx",
          name: "b.xlsx",
          has_children: true,
          size_bytes: 4096,
          representations: [],
        },
      ])
    )

    expect(node.role).toBe("container")
    expect(node.icon).toBe("folder_open")
  })

  it("keeps id and name", () => {
    const nodes: CatalogNode[] = [
      { kind: "schema", id: "public", name: "public", has_children: true, representations: [] },
    ]

    const node = first(toListNodes(nodes))

    expect(node.id).toBe("public")
    expect(node.label).toBe("public")
  })

  it("shows the row estimate of a table as the caption", () => {
    const node = first(
      toListNodes([
        {
          kind: "table",
          id: "public.users",
          name: "users",
          has_children: true,
          row_count_estimate: 1234,
          representations: [{ kind: "table", title: "View as table" }],
        },
      ])
    )

    expect(node.caption).toContain("1234")
  })

  it("says so in the same column when a table has no estimate yet", () => {
    const node = first(
      toListNodes([
        {
          kind: "table",
          id: "public.users",
          name: "users",
          has_children: true,
          row_count_estimate: null,
          representations: [{ kind: "table", title: "View as table" }],
        },
      ])
    )

    // Filled rather than blank: a column empty on some rows reads as one
    // nobody filled in, and "no answer" must not look like "no rows".
    expect(node.caption).toBe("N/A")
    expect(node.captionHint).toContain("analysed")
  })

  it("says where a declared table reads instead of a count nobody made (D170)", () => {
    const node = first(
      toListNodes([
        {
          kind: "table",
          id: "t0:user:",
          name: "users",
          has_children: false,
          declared_over: "user:",
          representations: [{ kind: "table", title: "View what it holds" }],
        },
      ])
    )

    expect(node.caption).toBe("over user:")
    expect(node.captionHint).toBe("Declared over the hashes in user:, one row each")
  })

  it("draws a hypertable as Timescale and a plain table as a table", () => {
    const [plain, hyper] = toListNodes([
      {
        kind: "table",
        id: "public.events",
        name: "events",
        has_children: true,
        representations: [{ kind: "table", title: "View as table" }],
      },
      {
        kind: "table",
        id: "public.metrics",
        name: "metrics",
        has_children: true,
        representations: [{ kind: "table", title: "View as table" }],
        specialization: { kind: "timescale_hypertable" },
      },
    ])

    expect(plain?.icon).toBe(ICONS.table)
    expect(hyper?.icon).toBe(TIMESCALE_ICON)
  })

  it("draws a continuous aggregate as Timescale, not as a stored view", () => {
    const [plain, aggregate] = toListNodes([
      {
        kind: "view",
        id: "public.daily",
        name: "daily",
        has_children: true,
        is_materialized: true,
        representations: [{ kind: "table", title: "View as table" }],
      },
      {
        kind: "view",
        id: "public.hourly",
        name: "hourly",
        has_children: true,
        is_materialized: true,
        representations: [{ kind: "table", title: "View as table" }],
        specialization: { kind: "timescale_continuous_aggregate" },
      },
    ])

    expect(plain?.icon).toBe(MATERIALIZED_VIEW_ICON)
    expect(aggregate?.icon).toBe(TIMESCALE_ICON)
  })

  it("distinguishes a materialized view from a plain one", () => {
    const plain = first(
      toListNodes([
        {
          kind: "view",
          id: "v",
          name: "v",
          has_children: true,
          representations: [{ kind: "table", title: "View as table" }],
        },
      ])
    )
    const materialized = first(
      toListNodes([
        {
          kind: "view",
          id: "m",
          name: "m",
          has_children: true,
          is_materialized: true,
          representations: [{ kind: "table", title: "View as table" }],
        },
      ])
    )

    // By its icon and by nothing else, the way every other kind says what it
    // is. A word beside the eye made the view the one row in the list that
    // named its kind twice.
    expect(plain.icon).toBe(ICONS.view)
    expect(materialized.icon).toBe(MATERIALIZED_VIEW_ICON)
    // Both stand in the counted column with a word saying nothing is stored
    // to count, which is the question a table answers with an estimate.
    expect(plain.caption).toBe("N/A")
    expect(materialized.caption).toBe("N/A")
    expect(plain.captionHint).toContain("stores no rows")
  })

  it("gives every visible kind its own icon", () => {
    const icons = toListNodes([
      { kind: "schema", id: "s", name: "s", has_children: true, representations: [] },
      {
        kind: "table",
        id: "t",
        name: "t",
        has_children: true,
        representations: [{ kind: "table", title: "View as table" }],
      },
      {
        kind: "view",
        id: "v",
        name: "v",
        has_children: true,
        representations: [{ kind: "table", title: "View as table" }],
      },
      { kind: "directory", id: "d", name: "d", has_children: true, representations: [] },
    ]).map((node) => node.icon)

    expect(new Set(icons).size).toBe(4)
  })

  it("carries the row estimate only for tables", () => {
    const mapped = toListNodes([
      { kind: "schema", id: "s", name: "s", has_children: true, representations: [] },
      {
        kind: "table",
        id: "t",
        name: "t",
        has_children: true,
        row_count_estimate: 12,
        representations: [{ kind: "table", title: "View as table" }],
      },
    ])

    expect(at(mapped, 0).rowEstimate).toBeNull()
    expect(at(mapped, 1).rowEstimate).toBe(12)
  })
})

describe("file sources", () => {
  it("labels a directory and does not call it readable", () => {
    const node = first(
      toListNodes([
        {
          kind: "directory",
          id: "reports",
          name: "reports",
          has_children: true,
          representations: [],
        },
      ])
    )

    expect(node.label).toBe("reports")
    expect(node.role).toBe("container")
    expect(node.readable).toBe(false)
  })

  it("shows the size of a file as the caption", () => {
    const node = first(
      toListNodes([
        {
          kind: "file",
          id: "reports/q3.csv",
          name: "q3.csv",
          has_children: false,
          size_bytes: 2048,
          representations: [{ kind: "table", title: "View as table" }],
        },
      ])
    )

    expect(node.caption).toContain("2")
    expect(node.caption).toMatch(/KB/i)
  })

  it("marks a readable file as readable and an opaque one as not", () => {
    const mapped = toListNodes([
      {
        kind: "file",
        id: "a.csv",
        name: "a.csv",
        has_children: false,
        size_bytes: 1,
        representations: [{ kind: "table", title: "View as table" }],
      },
      {
        kind: "file",
        id: "b.txt",
        name: "b.txt",
        has_children: false,
        size_bytes: 1,
        representations: [
          { kind: "text", title: "View as text" },
          { kind: "table", title: "View as table" },
        ],
      },
      {
        kind: "file",
        id: "c.png",
        name: "c.png",
        has_children: false,
        size_bytes: 1,
        representations: [],
      },
    ])

    expect(at(mapped, 0).readable).toBe(true)
    expect(at(mapped, 1).readable).toBe(true)
    expect(at(mapped, 2).readable).toBe(false)
  })

  it("has no row estimate for a file: counting rows means reading it", () => {
    const node = first(
      toListNodes([
        {
          kind: "file",
          id: "a.csv",
          name: "a.csv",
          has_children: false,
          size_bytes: 1,
          representations: [{ kind: "table", title: "View as table" }],
        },
      ])
    )

    expect(node.rowEstimate).toBeNull()
  })

  it("tells the three kinds of file apart by icon", () => {
    const icons = toListNodes([
      {
        kind: "file",
        id: "a.csv",
        name: "a.csv",
        has_children: false,
        size_bytes: 1,
        representations: [{ kind: "table", title: "View as table" }],
      },
      {
        kind: "file",
        id: "b.txt",
        name: "b.txt",
        has_children: false,
        size_bytes: 1,
        representations: [{ kind: "text", title: "View as text" }],
      },
      {
        kind: "file",
        id: "c.png",
        name: "c.png",
        has_children: false,
        size_bytes: 1,
        representations: [],
      },
    ]).map((node) => node.icon)

    expect(new Set(icons).size).toBe(3)
  })

  it("marks a table and a view as readable and a schema as not", () => {
    const mapped = toListNodes([
      {
        kind: "table",
        id: "t",
        name: "t",
        has_children: true,
        representations: [{ kind: "table", title: "View as table" }],
      },
      {
        kind: "view",
        id: "v",
        name: "v",
        has_children: true,
        representations: [{ kind: "table", title: "View as table" }],
      },
      { kind: "schema", id: "s", name: "s", has_children: true, representations: [] },
    ])

    expect(at(mapped, 0).readable).toBe(true)
    expect(at(mapped, 1).readable).toBe(true)
    expect(at(mapped, 2).readable).toBe(false)
  })

  it("shows where we are once a step has been taken", () => {
    expect(showsPath(2, [group("public")])).toBe(true)
  })

  it("shows the path at the top of a level that offers no groupings", () => {
    // A personal directory: nothing to filter by, so the head has room for
    // the path and it is there before the first step rather than appearing
    // on it. Read off what the level holds, never off the type of source.
    expect(showsPath(1, [])).toBe(true)
  })

  it("hides a path of one step next to a choice of groupings", () => {
    // A database at its root: the head says which schema is on, and a path
    // of one step beside it would say nothing.
    expect(showsPath(1, [group("public")])).toBe(false)
  })

  it("writes the path of a level from the root of the connection", () => {
    expect(levelPath("reports/2026")).toBe("/reports/2026")
  })

  it("calls the root itself a path", () => {
    // The level nothing has been opened from is still somewhere, and "/" is
    // what its owner would type into the folder of a connection.
    expect(levelPath(null)).toBe("/")
  })

  it("walks into the section of reports and opens a report", () => {
    // One kind covers both, as `entry` does for an archive: the section has
    // children and a report does not (D55).
    const section: CatalogNode = {
      kind: "report",
      id: "pg_dataplayer",
      name: "System",
      has_children: true,
      representations: [],
    }
    const report: CatalogNode = {
      kind: "report",
      id: "pg_dataplayer.processes",
      name: "Processes",
      description: "Backends connected now",
      has_children: false,
      representations: [{ kind: "table", title: "View as table" }],
    }

    expect(roleOf(section)).toBe("container")
    expect(roleOf(report)).toBe("leaf")

    const mapped = toListNodes([section, report])
    expect(at(mapped, 0).readable).toBe(false)
    expect(at(mapped, 1).readable).toBe(true)
    // The source writes the line; the list does not invent one.
    expect(at(mapped, 0).caption).toBeUndefined()
    expect(at(mapped, 1).caption).toBe("Backends connected now")
    expect(at(mapped, 0).icon).not.toBe(at(mapped, 1).icon)
  })
})

describe("the icons a catalog row draws", () => {
  /**
   * Every name must exist in the Symbols Outlined font.
   *
   * An unsupported name makes `q-icon` draw the literal word, which overflows
   * its 18px box and covers the tick box beside it. The bundled list keys
   * `grid_on` as `symOutlinedGridOn`.
   */
  it("are all in the bundled font", () => {
    const bundled: unknown = bundledIcons
    const known = new Set(
      Array.isArray(bundled) ? (bundled as string[]) : Object.keys(bundled as object)
    )
    const keyOf = (name: string) =>
      "symOutlined" + name.split("_").map((part) => part[0]?.toUpperCase() + part.slice(1)).join("")

    const used = [...Object.values(ICONS), REPORT_SECTION_ICON, MATERIALIZED_VIEW_ICON]
    expect(used.length).toBeGreaterThan(0)
    expect(used.filter((name) => !known.has(keyOf(name)))).toEqual([])
  })
})
