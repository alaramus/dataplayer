import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import type { ActionCommand } from "@/features/catalog/actions"
import { AppToggle } from "@/shared/ui"
import { withWindowHost } from "@/shared/testing/windows"

import ActionDialog from "./ActionDialog.vue"

const DROP: ActionCommand = {
  name: "drop_relation",
  label: "Drop",
  destructive: true,
  takesFile: false,
  previews: true,
  actsOn: "node",
  fields: [
    {
      name: "cascade",
      label: "Also drop everything built on it",
      kind: "boolean",
      required: false,
      defaultValue: false,
      group: "general",
    },
  ],
}

function mountDialog(command: ActionCommand = DROP, nodeIds = ["demo.customers"]) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(
    withWindowHost(ActionDialog, {
      command,
      connectorId: "c-1",
      nodeIds,
      nodeLabel: "customers",
    }),
    {
      global: {
        plugins: [
          [Quasar, { plugins: { Dialog, Notify } }],
          [VueQueryPlugin, { queryClient }],
        ],
      },
    }
  )
}

/** The dialog waits before asking, so the wait has to pass in the test too. */
async function settle() {
  await vi.advanceTimersByTimeAsync(300)
  await flushPromises()
}

function text(testid: string): string {
  return document.body.querySelector(`[data-testid="${testid}"]`)?.textContent ?? ""
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("what an action would do", () => {
  it("asks the source, and shows what it said in its own words", async () => {
    const preview = vi.spyOn(ConnectorsService, "previewAction").mockResolvedValue({
      data: {
        summary: "Something else is built on this relation",
        items: ["view demo.rich_customers depends on table demo.customers"],
        blocked: true,
      },
    } as never)
    const wrapper = mountDialog()
    await settle()

    expect(preview).toHaveBeenCalledWith({
      path: { connector_id: "c-1", action_name: "drop_relation" },
      body: { node_id: "demo.customers", params: { cascade: false } },
    })
    expect(text("action-preview")).toContain("rich_customers")
    wrapper.unmount()
  })

  it("turns the button off while the source says it would refuse", async () => {
    vi.spyOn(ConnectorsService, "previewAction").mockResolvedValue({
      data: { summary: "no", items: [], blocked: true },
    } as never)
    const wrapper = mountDialog()
    await settle()

    const submit = document.body.querySelector<HTMLButtonElement>(
      '[data-testid="action-submit"]'
    )
    expect(submit?.disabled).toBe(true)
    wrapper.unmount()
  })

  it("asks again when the form changes, because the answer is about it", async () => {
    const preview = vi.spyOn(ConnectorsService, "previewAction").mockResolvedValue({
      data: { summary: "fine", items: [], blocked: false },
    } as never)
    const wrapper = mountDialog()
    await settle()

    wrapper.findComponent(AppToggle).vm.$emit("update:modelValue", true)
    await settle()

    expect(preview.mock.calls.map(([request]) => request.body.params)).toEqual([
      { cascade: false },
      { cascade: true },
    ])
    wrapper.unmount()
  })

  it("says nothing about an action that cannot be asked", async () => {
    const preview = vi.spyOn(ConnectorsService, "previewAction")
    const wrapper = mountDialog({ ...DROP, previews: false })
    await settle()

    expect(preview).not.toHaveBeenCalled()
    expect(document.body.querySelector('[data-testid="action-preview"]')).toBeNull()
    wrapper.unmount()
  })

  it("does not ask about a form that is applied to several nodes", async () => {
    const preview = vi.spyOn(ConnectorsService, "previewAction")
    const wrapper = mountDialog(DROP, ["a", "b"])
    await settle()

    expect(preview).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it("says it could not find out, and still lets the action be run", async () => {
    vi.spyOn(ConnectorsService, "previewAction").mockRejectedValue(new Error("nope"))
    const wrapper = mountDialog()
    await settle()

    expect(text("action-preview-error")).not.toBe("")
    const submit = document.body.querySelector<HTMLButtonElement>(
      '[data-testid="action-submit"]'
    )
    expect(submit?.disabled).toBe(false)
    wrapper.unmount()
  })
})
