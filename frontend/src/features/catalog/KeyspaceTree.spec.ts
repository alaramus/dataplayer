import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"

import KeyspaceTree from "./KeyspaceTree.vue"

const KEY = {
  kind: "key",
  id: "k0:greeting",
  name: "greeting",
  data_type: "string",
  representations: [{ kind: "table", title: "View what it holds" }],
}

const FOLDER = {
  kind: "directory",
  id: "f0:cache:",
  name: "cache:",
  has_children: true,
  representations: [],
}

function mountTree() {
  vi.spyOn(ConnectorsService, "readCatalog").mockResolvedValue({
    data: [FOLDER, KEY],
  } as never)
  return mount(KeyspaceTree, {
    props: { connectorId: "c1", rootId: "d0" },
    global: {
      plugins: [
        Quasar,
        [
          VueQueryPlugin,
          {
            queryClient: new QueryClient({
              defaultOptions: { queries: { retry: false, gcTime: 0 } },
            }),
          },
        ],
      ],
    },
  })
}

/**
 * The whole row is the target, not the arrow beside it.
 *
 * The menu of actions acts on the selection, so a tree where nothing looks
 * selected is a menu whose subject is invisible — and reaching for a
 * ten-pixel arrow to see what is in a namespace is what made this feel stiff.
 */
describe("clicking a row of the key space", () => {
  it("marks what the actions would be done to", async () => {
    const wrapper = mountTree()
    await flushPromises()

    const row = wrapper.get('[data-testid="keyspace-row-k0:greeting"]')
    expect(row.attributes("aria-selected")).toBe("false")

    await row.trigger("click")

    expect(
      wrapper.get('[data-testid="keyspace-row-k0:greeting"]').attributes("aria-selected")
    ).toBe("true")
  })

  it("opens a key rather than expanding it", async () => {
    const wrapper = mountTree()
    await flushPromises()

    await wrapper.get('[data-testid="keyspace-row-k0:greeting"]').trigger("click")

    expect(wrapper.emitted("open")?.length).toBe(1)
    expect(wrapper.emitted("select")?.at(-1)?.[0]).toMatchObject({ id: "k0:greeting" })
  })

  it("opens and closes a namespace by its name", async () => {
    const wrapper = mountTree()
    await flushPromises()

    const folder = '[data-testid="keyspace-row-f0:cache:"]'
    await wrapper.get(folder).trigger("click")
    await flushPromises()
    // Nothing is opened in a tab: a namespace is a place, and what it holds is
    // what a click on it asks for.
    expect(wrapper.emitted("open")).toBeUndefined()
    expect(wrapper.get(folder).attributes("aria-selected")).toBe("true")

    // And the same click again puts it back, which is what a tree does —
    // without letting go of the selection, which is what the menu of actions
    // is about.
    await wrapper.get(folder).trigger("click")
    await flushPromises()
    expect(wrapper.get(folder).attributes("aria-selected")).toBe("true")
  })

  it("asks the tree to open a branch rather than marking it open", async () => {
    // Setting the expanded keys from outside marks a branch open and asks for
    // nothing, so a branch that loads its children when it opens stayed shut
    // with its arrow pointing the wrong way.
    const wrapper = mountTree()
    await flushPromises()
    const listing = vi.spyOn(ConnectorsService, "readCatalog").mockResolvedValue({
      data: [{ ...KEY, id: "k0:cache:one", name: "one" }],
    } as never)

    await wrapper.get('[data-testid="keyspace-row-f0:cache:"]').trigger("click")
    await flushPromises()

    expect(listing).toHaveBeenCalledWith(
      expect.objectContaining({ query: expect.objectContaining({ node_id: "f0:cache:" }) })
    )
  })
})

describe("pointing the key space at a key", () => {
  it("opens the folders on the way to a key it is told to show, and selects the key", async () => {
    // Walking the catalog into the folder instead left the tree rooted in no
    // database, and it drew every database at once.
    Element.prototype.scrollIntoView = vi.fn()
    const wrapper = mountTree()
    await flushPromises()
    vi.spyOn(ConnectorsService, "readCatalog").mockImplementation((async ({ query }: { query?: { node_id?: string | null } }) => ({
      data: query?.node_id === "f0:cache:"
        ? [{ ...FOLDER, id: "f0:cache:user:", name: "user:" }]
        : [{ ...KEY, id: "k0:cache:user:1", name: "1" }],
    })) as never)

    await (wrapper.vm as unknown as { reveal: (branches: string[], id: string) => Promise<void> })
      .reveal(["f0:cache:", "f0:cache:user:"], "k0:cache:user:1")
    await flushPromises()

    expect(
      wrapper.get('[data-testid="keyspace-row-k0:cache:user:1"]').attributes("aria-selected")
    ).toBe("true")
    expect(wrapper.emitted("select")?.at(-1)?.[0]).toMatchObject({ id: "k0:cache:user:1" })
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled()
  })
})
