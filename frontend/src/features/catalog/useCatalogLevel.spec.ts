import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { defineComponent, h, ref } from "vue"

import { ConnectorsService } from "@/client"
import { at, first } from "@/shared/testing/collections"
import { useCatalogLevel } from "./useCatalogLevel"
import type { CatalogLevel } from "./useCatalogLevel"

beforeEach(() => {
  // The spy is the same object across tests, so queued one-shot answers would
  // otherwise be handed to whichever test ran next.
  vi.restoreAllMocks()
})

function withLevel(run: (level: CatalogLevel) => Promise<void>) {
  return new Promise<void>((resolve, reject) => {
    const Host = defineComponent({
      setup() {
        const level = useCatalogLevel(ref("c1"), ref("mydb"))
        run(level).then(resolve).catch(reject)
        return () => h("div")
      },
    })
    mount(Host, {
      global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] },
    })
  })
}

const table = (id: string, name: string) => ({
  id,
  name,
  kind: "table" as const,
  has_children: false,
  row_count_estimate: 10,
  representations: [{ kind: "table" as const, title: "View as table" }],
})

const schema = (name: string, isSystem = false) => ({
  id: name,
  name,
  kind: "schema" as const,
  has_children: true,
  is_system: isSystem,
  representations: [],
})

const database = (index: number, preferred = false) => ({
  id: `d${String(index)}`,
  name: `db${String(index)}`,
  kind: "database" as const,
  has_children: true,
  preferred,
  keys: 0,
  representations: [],
})

const directory = (id: string, name: string) => ({
  id,
  name,
  kind: "directory" as const,
  has_children: true,
  representations: [],
})

/** One answer per call, in order, whatever node was asked about. */
function answers(...pages: unknown[][]) {
  const spy = vi.spyOn(ConnectorsService, "readCatalog")
  for (const page of pages) spy.mockResolvedValueOnce({ data: page } as never)
  return spy
}

describe("walking a catalog", () => {
  it("lists the children of the root", async () => {
    answers([table("public.orders", "orders")])

    await withLevel(async (level) => {
      await level.load()

      expect(level.items.value.map((node) => node.label)).toEqual(["orders"])
      expect(level.error.value).toBe("")
    })
  })

  it("keeps the reason a level could not be read", async () => {
    vi.spyOn(ConnectorsService, "readCatalog").mockRejectedValue(new Error("no route to host"))

    await withLevel(async (level) => {
      await level.load()

      expect(level.items.value).toEqual([])
      expect(level.error.value).not.toBe("")
    })
  })

  it("walks into a directory and back out again", async () => {
    answers(
      [directory("reports", "reports")],
      [table("reports/q3.csv", "q3.csv")],
      [directory("reports", "reports")]
    )

    await withLevel(async (level) => {
      await level.load()
      await level.enter(first(level.items.value))

      expect(level.currentId.value).toBe("reports")
      expect(level.path.value.map((crumb) => crumb.label)).toEqual(["mydb", "reports"])

      await level.up()

      expect(level.currentId.value).toBeNull()
      expect(level.path.value).toHaveLength(1)
    })
  })

  it("does not walk into something that opens instead", async () => {
    answers([table("public.orders", "orders")])

    await withLevel(async (level) => {
      await level.load()
      await level.enter(first(level.items.value))

      expect(level.currentId.value).toBeNull()
    })
  })
})

describe("groupings", () => {
  it("turns schemas into a filter and shows every real one while there are few", async () => {
    // A database with two or three schemas is one where a person wants to see
    // what is in it. A server this application started has `public` and the
    // demonstration schema, and showing only the empty one of the two is
    // showing nothing.
    // Three answers for three readings: the level itself, and then the
    // children of each grouping that opens. A page short and the spy falls
    // through to a real request, which is a network error rather than an
    // empty list.
    answers(
      [schema("pg_catalog", true), schema("public"), schema("sales")],
      [table("public.orders", "orders")],
      []
    )

    await withLevel(async (level) => {
      await level.load()

      expect(level.groups.value.map((group) => group.id)).toEqual(["pg_catalog", "public", "sales"])
      expect(level.selectedGroups.value).toEqual(["public", "sales"])
      expect(level.items.value.map((node) => node.label)).toEqual(["orders"])
    })
  })

  it("opens on the choice made last time rather than on the default", async () => {
    // The default rule is for a connection nobody has an opinion about yet.
    // Turning a schema off and finding it back after a reload is the
    // application overruling the person.
    answers([schema("pg_catalog", true), schema("public"), schema("sales")], [])

    await withLevel(async (level) => {
      await level.load(["sales"])

      expect(level.selectedGroups.value).toEqual(["sales"])
    })
  })

  it("goes back to the default when nothing that was chosen is there any more", async () => {
    // Three answers for three readings, as above: the level, and then the
    // children of each of the two schemas the default turns back on. A page
    // short and the spy falls through to a real request, whose network error
    // would empty the choice rather than leave it at the default.
    answers([schema("public"), schema("sales")], [], [])

    await withLevel(async (level) => {
      await level.load(["gone"])

      expect(level.selectedGroups.value).toEqual(["public", "sales"])
    })
  })

  it("shows only the first when there are more than a handful", async () => {
    // Opening forty schemas at once is a page nobody asked for.
    const many = Array.from({ length: 8 }, (_, index) => schema(`s${String(index)}`))
    answers([schema("pg_catalog", true), ...many], [table("s0.orders", "orders")])

    await withLevel(async (level) => {
      await level.load()

      expect(level.selectedGroups.value).toEqual(["s0"])
    })
  })

  it("falls back to a system grouping when there is nothing else", async () => {
    answers([schema("pg_catalog", true)], [])

    await withLevel(async (level) => {
      await level.load()

      expect(level.selectedGroups.value).toEqual(["pg_catalog"])
    })
  })

  it("opens on the grouping the source named, however many there are", async () => {
    // Sixteen Redis databases, and the connection was written with one of
    // them in it. Nothing but the source knows which; opening on whichever is
    // listed first would throw away what the user chose.
    const all = Array.from({ length: 16 }, (_, index) => database(index, index === 3))
    answers(all, [])

    await withLevel(async (level) => {
      await level.load()

      expect(level.selectedGroups.value).toEqual(["d3"])
    })
  })

  it("says which grouping a row came from", async () => {
    answers([schema("public")], [table("public.orders", "orders")])

    await withLevel(async (level) => {
      await level.load()

      expect(first(level.items.value).group).toBe("public")
    })
  })

  it("shows the rows of every grouping that is on", async () => {
    // Only three answers: the second grouping is read, the first is already
    // in the cache and is not asked for again.
    answers(
      [schema("public"), schema("sales")],
      [table("public.orders", "orders")],
      [table("sales.leads", "leads")]
    )

    await withLevel(async (level) => {
      await level.load()
      await level.setGroups(["public", "sales"])

      expect(level.items.value.map((node) => node.label)).toEqual(["orders", "leads"])
    })
  })

  it("follows a selected grouping renamed by the source", async () => {
    answers(
      [schema("public"), schema("sales")],
      [table("public.orders", "orders")],
      [table("sales.leads", "leads")]
    )

    await withLevel(async (level) => {
      await level.load()
      await level.setGroups(["sales"])
      level.replaceNode({
        old_node_id: "sales",
        new_node_id: "archive",
        title: "archive",
      })

      expect(level.selectedGroups.value).toEqual(["archive"])
      expect(level.groups.value.map((group) => group.label)).toEqual([
        "public",
        "archive",
      ])
    })
  })
})

describe("what is ticked", () => {
  it("ticks everything the list is showing and unticks it again", async () => {
    answers([table("a", "a"), table("b", "b")])

    await withLevel(async (level) => {
      await level.load()
      level.toggleAll(true)

      expect(level.checked.value).toEqual(["a", "b"])
      expect(level.allChecked.value).toBe(true)

      level.toggleAll(false)

      expect(level.checked.value).toEqual([])
    })
  })

  it("ticks only what the filter left on screen", async () => {
    answers([table("a", "orders"), table("b", "leads")])

    await withLevel(async (level) => {
      await level.load()
      level.filter.value = "ord"
      level.toggleAll(true)

      expect(level.checked.value).toEqual(["a"])
    })
  })

  it("forgets what was ticked on the way to another level", async () => {
    answers([directory("reports", "reports")], [table("reports/q3.csv", "q3.csv")])

    await withLevel(async (level) => {
      await level.load()
      level.toggleAll(true)
      await level.enter(first(level.items.value))

      expect(level.checked.value).toEqual([])
    })
  })

  it("resolves what is ticked to the nodes themselves", async () => {
    answers([table("a", "a"), table("b", "b")])

    await withLevel(async (level) => {
      await level.load()
      level.checked.value = ["b"]

      expect(level.checkedNodes.value.map((node) => node.label)).toEqual(["b"])
    })
  })
})

describe("the filter", () => {
  it("keeps the rows whose name holds the text, whatever the case", async () => {
    answers([table("a", "Orders"), table("b", "leads")])

    await withLevel(async (level) => {
      await level.load()
      level.filter.value = "ORD"

      expect(level.items.value.map((node) => node.id)).toEqual(["a"])
    })
  })
})

describe("re-reading after a change", () => {
  it("shows what the level holds now, not what it held before", async () => {
    const spy = answers([table("a", "a"), table("b", "b")], [table("a", "a")])

    await withLevel(async (level) => {
      await level.load()
      await level.reload(null)

      expect(level.items.value.map((node) => node.id)).toEqual(["a"])
      expect(spy.mock.calls[1]?.[0].query).toEqual({ refresh: true })
    })
  })

  it("stays where it is rather than going back to the root", async () => {
    answers(
      [directory("reports", "reports")],
      [table("reports/q3.csv", "q3.csv")],
      [table("reports/q4.csv", "q4.csv")]
    )

    await withLevel(async (level) => {
      await level.load()
      await level.enter(first(level.items.value))
      await level.reload("reports")

      expect(level.currentId.value).toBe("reports")
      expect(at(level.items.value, 0).label).toBe("q4.csv")
    })
  })

  it("keeps a non-default schema selected after a relation changes", async () => {
    answers(
      [schema("public"), schema("sales")],
      [table("public.orders", "orders")],
      [table("sales.leads", "leads")],
      [schema("public"), schema("sales")],
      [table("sales.prospects", "prospects")]
    )

    await withLevel(async (level) => {
      await level.load()
      await level.setGroups(["sales"])
      await level.reload("sales")

      expect(level.selectedGroups.value).toEqual(["sales"])
      expect(level.items.value.map((node) => node.label)).toEqual(["prospects"])
    })
  })
})
describe("standing where a node lives", () => {
  it("walks to the level of the node and draws the trail to it", async () => {
    answers([table("reports/2026/q3.csv", "q3.csv")])

    await withLevel(async (level) => {
      await level.showLocation({
        crumbs: [
          { id: "reports", label: "reports" },
          { id: "reports/2026", label: "2026" },
        ],
        groups: [],
        parentId: "reports/2026",
      })

      expect(level.currentId.value).toBe("reports/2026")
      expect(level.path.value.map((crumb) => crumb.label)).toEqual(["mydb", "reports", "2026"])
    })
  })

  it("ticks the grouping the node lives under rather than the default one", async () => {
    // The root answers with two schemas; `sales` is not the one a fresh level
    // would have picked, so a location that names it must override the default.
    answers([schema("public"), schema("sales")], [table("sales.leads", "leads")])

    await withLevel(async (level) => {
      await level.showLocation({ crumbs: [], groups: ["sales"], parentId: null })

      expect(level.selectedGroups.value).toEqual(["sales"])
      expect(level.items.value.map((node) => node.label)).toEqual(["leads"])
    })
  })

  it("does not disturb a level that is already the right one", async () => {
    // Ticks are the user's, and pointing at a row that is already on screen
    // is no reason to take them away.
    const spy = answers(
      [schema("public")],
      [table("public.orders", "orders"), table("public.leads", "leads")]
    )

    await withLevel(async (level) => {
      await level.load()
      level.checked.value = ["public.orders"]
      const readsSoFar = spy.mock.calls.length

      await level.showLocation({ crumbs: [], groups: ["public"], parentId: null })

      expect(level.checked.value).toEqual(["public.orders"])
      expect(spy.mock.calls.length).toBe(readsSoFar)
    })
  })
})

describe("searching from a level", () => {
  const found = (name: string, location: string) => ({
    node: {
      id: location === "" ? name : `${location}/${name}`,
      name,
      kind: "file" as const,
      has_children: false,
      size_bytes: 4,
      representations: [{ kind: "text" as const, title: "View as text" }],
    },
    parent_id: location === "" ? null : location,
    location,
  })

  function searched(...matches: ReturnType<typeof found>[]) {
    return vi
      .spyOn(ConnectorsService, "searchCatalog")
      .mockResolvedValue({ data: { matches, complete: true, notice: null } } as never)
  }

  it("shows what was found instead of the level, and takes the words with it", async () => {
    answers([directory("reports", "reports")])
    const spy = searched(found("notes.txt", ""), found("q3-notes.md", "reports"))

    await withLevel(async (level) => {
      await level.load()
      level.filter.value = "notes"
      await level.search()

      expect(level.items.value.map((node) => node.label)).toEqual([
        "notes.txt",
        "q3-notes.md",
      ])
      expect(at(level.items.value, 1).location).toBe("reports")
      expect(spy).toHaveBeenCalledOnce()
    })
  })

  it("shows a file found by its contents, whose name holds none of the words", async () => {
    answers([directory("reports", "reports")])
    vi.spyOn(ConnectorsService, "searchCatalogContents").mockResolvedValue({
      data: {
        matches: [{ ...found("server.log", ""), excerpt: "checkpoint starting" }],
        complete: true,
        notice: null,
      },
    } as never)

    await withLevel(async (level) => {
      await level.load()
      level.filter.value = "checkpoint"
      await level.search("contents")

      // The words narrow a level; they do not narrow what was found with them.
      expect(level.items.value.map((node) => node.label)).toEqual(["server.log"])
      expect(level.items.value[0]?.caption).toBe("checkpoint starting")
    })
  })

  it("asks from the level being looked at, not from the top", async () => {
    answers([directory("reports", "reports")], [table("reports/q3.csv", "q3.csv")])
    const spy = searched()

    await withLevel(async (level) => {
      await level.load()
      await level.enter(first(level.items.value))
      level.filter.value = "notes"
      await level.search()

      expect(spy.mock.calls[0]?.[0]).toMatchObject({
        query: { node_id: "reports", query: "notes" },
      })
    })
  })

  it("does nothing without words to look for", async () => {
    answers([directory("reports", "reports")])
    const spy = searched()

    await withLevel(async (level) => {
      await level.load()
      level.filter.value = "   "
      await level.search()

      expect(spy).not.toHaveBeenCalled()
      expect(level.found.value).toBeNull()
    })
  })

  it("goes back to the level when the search is closed, keeping the words", async () => {
    answers([directory("reports", "reports")])
    searched(found("notes.txt", ""))

    await withLevel(async (level) => {
      await level.load()
      level.filter.value = "reports"
      await level.search()
      level.clearSearch()

      expect(level.found.value).toBeNull()
      // The words are a filter again, which is what they were before.
      expect(level.filter.value).toBe("reports")
      expect(level.items.value.map((node) => node.label)).toEqual(["reports"])
    })
  })

  it("ends a search by walking anywhere", async () => {
    answers(
      [directory("reports", "reports")],
      [table("reports/q3.csv", "q3.csv")]
    )
    // A folder that was found is walked into like any other row, and walking
    // is what ends a search.
    vi.spyOn(ConnectorsService, "searchCatalog").mockResolvedValue({
      data: {
        matches: [
          { node: directory("reports", "reports"), parent_id: null, location: "" },
        ],
        complete: true,
        notice: null,
      },
    } as never)

    await withLevel(async (level) => {
      await level.load()
      level.filter.value = "reports"
      await level.search()
      await level.enter(first(level.items.value))

      expect(level.found.value).toBeNull()
      expect(level.currentId.value).toBe("reports")
    })
  })

  it("keeps the reason a search could not be run", async () => {
    answers([directory("reports", "reports")])
    vi.spyOn(ConnectorsService, "searchCatalog").mockRejectedValue(new Error("gone"))

    await withLevel(async (level) => {
      await level.load()
      level.filter.value = "notes"
      await level.search()

      expect(level.found.value).toBeNull()
      expect(level.error.value).not.toBe("")
    })
  })

  it("ticks what a search found, so the menu acts on it", async () => {
    answers([directory("reports", "reports")])
    searched(found("notes.txt", "reports"))

    await withLevel(async (level) => {
      await level.load()
      level.filter.value = "notes"
      await level.search()
      level.checked.value = ["reports/notes.txt"]

      expect(level.checkedNodes.value.map((node) => node.id)).toEqual([
        "reports/notes.txt",
      ])
    })
  })
})
