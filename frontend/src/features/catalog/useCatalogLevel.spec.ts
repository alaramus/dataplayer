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
  it("turns schemas into a filter and shows the first real one", async () => {
    answers(
      [schema("pg_catalog", true), schema("public"), schema("sales")],
      [table("public.orders", "orders")]
    )

    await withLevel(async (level) => {
      await level.load()

      expect(level.groups.value.map((group) => group.id)).toEqual(["pg_catalog", "public", "sales"])
      expect(level.selectedGroups.value).toEqual(["public"])
      expect(level.items.value.map((node) => node.label)).toEqual(["orders"])
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
