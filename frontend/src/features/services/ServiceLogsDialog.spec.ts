import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"
import { defineComponent, Fragment, h, ref } from "vue"

import { provideWindows, useWindows, WindowHost } from "@/shared/windows"
import { workspaceActionsKey } from "@/features/workspace/state"
import type { WorkspaceActions } from "@/features/workspace/state"

import ServiceLogsDialog from "./ServiceLogsDialog.vue"

vi.mock("./api", () => ({
  useServiceLogs: () => ({
    data: ref({ lines: ["it started", "it stopped"] }),
    isLoading: ref(false),
    isFetching: ref(false),
    refetch: vi.fn(),
  }),
}))

const SERVICE = { id: "svc-1", connector_name: "warehouse" }

/**
 * The dialog behind the production `v-model:service`: moving to a tab emits
 * `update:service` with null, the parent clears the service, and only then
 * does the window close. A static prop would leave the window open forever,
 * so the harness owns the service the way ManagedServices does.
 */
function mountDialog(actions: Partial<WorkspaceActions> | null) {
  const Root = defineComponent({
    name: "ServiceLogsDialogTestRoot",
    emits: ["update:service"],
    setup(_, { emit }) {
      const windows = useWindows()
      provideWindows(windows)
      const service = ref<{ id: string; connector_name: string } | null>({ ...SERVICE })
      return () =>
        h(Fragment, [
          h(ServiceLogsDialog, {
            service: service.value,
            "onUpdate:service": (value: null) => {
              service.value = value
              emit("update:service", value)
            },
          }),
          h(WindowHost, { context: windows.context }),
        ])
    },
  })
  return mount(Root, {
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

    // WindowDialog renders through WindowHost, so the command lives in the
    // body rather than in the wrapper — the dashboard's detach test reads it
    // the same way.
    const toTab = document.body.querySelector<HTMLButtonElement>('[data-testid="window-to-tab"]')
    expect(toTab).not.toBeNull()
    toTab?.click()
    await flushPromises()

    expect(openServiceLogsTab).toHaveBeenCalledWith({
      serviceId: "svc-1",
      serviceName: "warehouse",
    })
    // A move, not a copy: the window is closed behind the tab.
    // Closing the window echoes the emission once more through the dialog's
    // own model binding, so only the first one is pinned.
    expect(wrapper.emitted("update:service")).toContainEqual([null])
    expect(document.body.querySelector('[data-testid="window-to-tab"]')).toBeNull()
    wrapper.unmount()
  })

  it("offers no way to a tab outside a workspace", async () => {
    const wrapper = mountDialog(null)
    await flushPromises()

    expect(document.body.querySelector('[data-testid="window-to-tab"]')).toBeNull()
    wrapper.unmount()
  })
})
