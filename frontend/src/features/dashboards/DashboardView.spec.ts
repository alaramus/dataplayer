import { flushPromises, mount } from "@vue/test-utils"
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"
import { ref } from "vue"

import type { DashboardPublic } from "@/client"
import { withWindowHost } from "@/shared/testing/windows"
import { workspaceActionsKey } from "@/features/workspace/state"
import type { WorkspaceActions } from "@/features/workspace/state"

import DashboardView from "./DashboardView.vue"

vi.mock("./api", () => ({
  dashboardsKey: ["dashboards"],
  useDashboardCatalog: () => ({ data: ref(undefined) }),
  useMetricsCatalog: () => ({ data: ref(undefined) }),
  useLivePoints: () => undefined,
  useSaveDashboard: () => ({ mutateAsync: vi.fn(async () => ({ version: 2 })) }),
  useDeleteDashboard: () => ({ mutateAsync: vi.fn() }),
  // Rendered dialogs this view always mounts stay shut, so their queries
  // never load and their mutations never run.
  useDashboardGrants: () => ({ data: ref([]), isLoading: ref(false) }),
  useWriteDashboardGrant: () => ({ mutateAsync: vi.fn(), isPending: ref(false) }),
  useRevokeDashboardGrant: () => ({ mutateAsync: vi.fn(), isPending: ref(false) }),
  usePresets: () => ({ data: ref([]), isPending: ref(false), isError: ref(false), error: ref(null) }),
}))

// jsdom has no layout, and with it no ResizeObserver.
class NoObservation {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal("ResizeObserver", NoObservation)

const WIDGET = {
  type: "stat" as const,
  id: "w1",
  title: "CPU",
  layout: { x: 0, y: 0, w: 3, h: 5 },
  series_id: 7,
}

const DASHBOARD = {
  id: "dash-1",
  name: "Fleet",
  version: 1,
  widgets: [WIDGET],
  options: { range_seconds: 900, refresh_seconds: 30 },
} as unknown as DashboardPublic

describe("DashboardView detaching a widget", () => {
  it("opens a window that offers to move its contents into a workspace tab (D155)", async () => {
    const openWidgetTab = vi.fn()
    const wrapper = mount(
      withWindowHost(DashboardView, {
        dashboard: DASHBOARD,
        catalog: undefined,
        index: new Map(),
      }),
      {
        global: {
          plugins: [Quasar, [VueQueryPlugin, { queryClient: new QueryClient() }]],
          provide: {
            [workspaceActionsKey as symbol]: { openWidgetTab } as unknown as WorkspaceActions,
          },
          stubs: { WidgetBody: { template: "<div />" } },
        },
      }
    )
    await flushPromises()

    await wrapper.get('[data-testid="widget-detach"]').trigger("click")
    await flushPromises()

    const toTab = document.body.querySelector<HTMLButtonElement>('[data-testid="window-to-tab"]')
    expect(toTab).not.toBeNull()
    toTab?.click()
    await flushPromises()

    expect(openWidgetTab).toHaveBeenCalledWith({
      dashboardId: "dash-1",
      widget: WIDGET,
      rangeSeconds: 900,
      refreshSeconds: 30,
    })
    // A move, not a copy: the window is closed behind the tab.
    expect(document.body.querySelector('[data-testid="window-to-tab"]')).toBeNull()
    wrapper.unmount()
  })
})
