import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { mount } from "@vue/test-utils"
import { describe, expect, it, vi } from "vitest"
import { defineComponent, h, ref } from "vue"

import { ConnectorsService } from "@/client"
import { useCatalogTree } from "./useCatalogTree"
import type { CatalogTree } from "./useCatalogTree"

function withTree(run: (tree: CatalogTree) => Promise<void>) {
  return new Promise<void>((resolve, reject) => {
    const Host = defineComponent({
      setup() {
        const tree = useCatalogTree(ref("c1"))
        run(tree).then(resolve).catch(reject)
        return () => h("div")
      },
    })
    mount(Host, {
      global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] },
    })
  })
}

const node = (id: string, name: string) => ({
  id,
  name,
  kind: "table" as const,
  has_children: true,
  row_count_estimate: 10,
})

describe("the catalog tree", () => {
  it("loads the roots", async () => {
    vi.spyOn(ConnectorsService, "readCatalog").mockResolvedValue({
      data: [node("public.orders", "orders")],
    } as never)

    await withTree(async (tree) => {
      await tree.load()
      expect(tree.roots.value.map((root) => root.label)).toEqual(["orders"])
      expect(tree.error.value).toBe("")
    })
  })

  it("keeps the reason a branch could not be read", async () => {
    vi.spyOn(ConnectorsService, "readCatalog").mockRejectedValue(new Error("no route to host"))

    await withTree(async (tree) => {
      await tree.load()
      expect(tree.roots.value).toEqual([])
      expect(tree.error.value).not.toBe("")
    })
  })

  it("drops a selection the reload no longer holds", async () => {
    vi.spyOn(ConnectorsService, "readCatalog")
      .mockResolvedValueOnce({ data: [node("a", "a"), node("b", "b")] } as never)
      .mockResolvedValueOnce({ data: [node("a", "a")] } as never)

    await withTree(async (tree) => {
      await tree.load()
      tree.selectedId.value = "b"
      await tree.reload(null)
      expect(tree.selectedId.value).toBeNull()
    })
  })

  it("resolves a selection to the node it names", async () => {
    vi.spyOn(ConnectorsService, "readCatalog").mockResolvedValue({
      data: [node("a", "orders")],
    } as never)

    await withTree(async (tree) => {
      await tree.load()
      tree.selectedId.value = "a"
      expect(tree.selected.value?.label).toBe("orders")
    })
  })
})
