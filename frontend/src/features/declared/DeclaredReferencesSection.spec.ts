import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { DeclaredReferencesService } from "@/client"
import { withWindowHost } from "@/shared/testing/windows"

import DeclaredReferencesSection from "./DeclaredReferencesSection.vue"

const REFERENCE = {
  id: "ref-1",
  created_at: null,
  ends: [
    {
      connector_id: "warehouse",
      node_id: "demo_lab.organizations",
      column: "slug",
      connector_name: "PostgreSQL",
      adapter_type: "postgres",
      node_label: "organizations",
    },
    {
      connector_id: "files",
      node_id: "accounts.csv",
      column: "slug",
      connector_name: "Files",
      adapter_type: "file",
      node_label: "accounts.csv",
    },
  ],
}

function mountSection() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(
    withWindowHost(DeclaredReferencesSection, {
      connectorId: "warehouse",
      nodeId: "demo_lab.organizations",
      nodeLabel: "organizations",
    }),
    {
      global: {
        plugins: [[Quasar, { plugins: { Dialog, Notify } }], [VueQueryPlugin, { queryClient }]],
      },
    }
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(DeclaredReferencesService, "referencesListDeclaredReferences").mockResolvedValue({
    data: [REFERENCE],
  } as never)
})

describe("the references drawn from one node", () => {
  it("reads from the end being stood on", async () => {
    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.get('[data-testid="declared-reference"]').text()).toContain(
      "slug → Files · accounts.csv.slug"
    )
    wrapper.unmount()
  })

  it("removes one only after it is confirmed", async () => {
    const removed = vi
      .spyOn(DeclaredReferencesService, "referencesUndeclareReference")
      .mockResolvedValue({ data: { message: "Declared reference removed" } } as never)
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('[data-testid="declared-remove-ref-1"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="confirm-accept"]')?.click()
    await flushPromises()

    expect(removed).toHaveBeenCalledWith({ path: { reference_id: "ref-1" } })
    wrapper.unmount()
  })

  it("keeps it when the question is answered no", async () => {
    const removed = vi
      .spyOn(DeclaredReferencesService, "referencesUndeclareReference")
      .mockResolvedValue({ data: { message: "Declared reference removed" } } as never)
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('[data-testid="declared-remove-ref-1"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="confirm-cancel"]')?.click()
    await flushPromises()

    expect(removed).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="declared-reference"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
