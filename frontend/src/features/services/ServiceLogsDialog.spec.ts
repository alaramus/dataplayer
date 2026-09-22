import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"
import { ref } from "vue"

import { withWindowHost } from "@/shared/testing/windows"
import { workspaceActionsKey } from "@/features/workspace/state"
import type { WorkspaceActions } from "@/features/workspace/state"

import ServiceLogsDialog from "./ServiceLogsDialog.vue"

vi.mock("./api", () => ({
  useServiceLogs: () => ({
    data: ref({ lines: ["it started", "it stopped"] }),
    isLoading: ref(false),
  }),
}))

const SERVICE = { id: "svc-1", connector_name: "warehouse" }

function mountDialog(actions: Partial<WorkspaceActions> | null) {
  return mount(withWindowHost(ServiceLogsDialog, { service: SERVICE }), {
    global: {
      plugins: [Quasar],
      ...(actions === null
        ? {}
        : { provide: { [workspaceActionsKey as symbol]: actions as WorkspaceActions } }),
    },
  })
}

describe("ServiceLogsDialog", () => {
  it("offers to move the window's contents into a workspace tab (D155)", async () => {
    const openServiceLogsTab = vi.fn()
    const wrapper = mountDialog({ openServiceLogsTab })
    await flushPromises()

    await wrapper.get('[data-testid="window-to-tab"]').trigger("click")

    expect(openServiceLogsTab).toHaveBeenCalledWith({
      serviceId: "svc-1",
      serviceName: "warehouse",
    })
    // A move, not a copy: the window is closed behind the tab.
    expect(wrapper.emitted("update:service")).toEqual([[null]])
    expect(wrapper.find('[data-testid="window-to-tab"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("offers no way to a tab outside a workspace", async () => {
    const wrapper = mountDialog(null)
    await flushPromises()

    expect(wrapper.find('[data-testid="window-to-tab"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
