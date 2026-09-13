import { DOMWrapper, flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent, h, inject, onBeforeUnmount, onDeactivated, provide, ref } from "vue"
import type { Component } from "vue"
import { afterEach, describe, expect, it, vi } from "vitest"
import { z } from "zod"

import { provideWindows, useWindows, WindowHost } from "@/shared/windows"
import type { WindowsApi } from "@/shared/windows"
import WindowTaskbar from "@/shared/windows/WindowTaskbar.vue"

import { makeLeaf, makeSplit } from "./model"
import { useWorkspace } from "./useWorkspace"
import type { WorkspaceApi } from "./useWorkspace"
import WorkspaceDetachTarget from "./WorkspaceDetachTarget.vue"
import WorkspaceRoot from "./WorkspaceRoot.vue"

const schema = z.object({ id: z.string(), title: z.string(), kind: z.string() })
type Panel = z.infer<typeof schema>
const cleanups: Array<() => void> = []

afterEach(() => {
  for (const cleanup of cleanups.splice(0)) cleanup()
  localStorage.clear()
})

async function fixture() {
  const mounted = vi.fn()
  const disposed = vi.fn()
  const deactivated = vi.fn()
  const mayClose = vi.fn(() => true)
  const components = new Map<string, Component>()
  const covered = ref(false)
  let api: { workspace: WorkspaceApi<Panel>; windows: WindowsApi } | null = null
  const Root = defineComponent({
    setup() {
      provide("page-context", "kept")
      const windows = useWindows()
      provideWindows(windows)
      const workspace = useWorkspace<Panel>({
        storageKey: "detachment-component-test", panelSchema: schema,
        defaults: () => ({
          tree: makeSplit("root", "row", [
            makeLeaf("sources", ["p1"], { pinned: true, accepts: "sources" }),
            makeLeaf("work", ["p2", "p3"], { pinned: true, accepts: "work" }),
          ], [25, 75]),
          panels: [
            { id: "p1", title: "Sources", kind: "sources" },
            { id: "p2", title: "Orders", kind: "work" },
            { id: "p3", title: "Customers", kind: "work" },
          ],
        }),
        kindOf: (panel) => panel.kind,
        look: (panel) => ({ title: panel.title, icon: "table_chart", closable: panel.id !== "p1" }),
        beforeClose: mayClose,
        // Kept under the engine's key rather than the panel's id, exactly as
        // the application does: a renamed panel is the same panel.
        component: (panel, key) => {
          let component = components.get(key)
          if (component === undefined) {
            component = defineComponent({
              setup() {
                const page = inject("page-context")
                const value = ref("")
                mounted(panel.id)
                onBeforeUnmount(() => disposed(panel.id))
                onDeactivated(() => deactivated(panel.id))
                return () => h("input", {
                  "aria-label": `Draft ${panel.id}`, "data-page-context": page,
                  "data-panel-title": panel.title,
                  value: value.value,
                  onInput: (event: Event) => { value.value = (event.target as HTMLInputElement).value },
                })
              },
            })
            components.set(key, component)
          }
          return component
        },
      })
      api = { workspace, windows }
      return () => h("div", [
        h("header", [h(WorkspaceDetachTarget, { context: workspace.context })]),
        h(WorkspaceRoot, { context: workspace.context, covered: covered.value }, {
          cover: () => h("div", { "data-testid": "cover" }, "Something else"),
        }),
        h(WindowHost, { context: windows.context }),
        h(WindowTaskbar, { context: windows.context }),
      ])
    },
  })
  const container = document.createElement("div")
  document.body.append(container)
  const wrapper = mount(Root, { attachTo: container, global: { plugins: [Quasar] } })
  cleanups.push(() => { wrapper.unmount(); container.remove() })
  await flushPromises()
  if (api === null) throw new Error("The workspace did not mount")
  return { ...(api as { workspace: WorkspaceApi<Panel>; windows: WindowsApi }),
    body: new DOMWrapper(document.body), mounted, disposed, deactivated, mayClose, covered }
}

describe("moving a live panel between the workspace and a window", () => {
  it("parks every panel alive while something else covers the sections", async () => {
    // D125: the dashboards take the room of the sections, and a draft, a grid
    // page or a transaction in the workspace must still be there afterwards.
    const { body, covered, disposed, deactivated } = await fixture()
    const input = body.get('input[aria-label="Draft p2"]')
    await input.setValue("still here")

    covered.value = true
    await flushPromises()

    expect(body.find('[data-testid="cover"]').exists()).toBe(true)
    expect(body.find('[data-testid="workspace-leaf-work"]').exists()).toBe(false)
    expect(deactivated).toHaveBeenCalledWith("p2")
    expect(disposed).not.toHaveBeenCalled()

    covered.value = false
    await flushPromises()

    const back = body.get('[data-testid="workspace-leaf-work"] input')
    expect(back.element).toBe(input.element)
    expect((back.element as HTMLInputElement).value).toBe("still here")
  })

  it("restores a saved layout with common drafts alive and unrelated windows still open", async () => {
    const { workspace, windows, body, disposed, mayClose } = await fixture()
    const saved = workspace.snapshot()
    const input = body.get('input[aria-label="Draft p2"]')
    await input.setValue("kept across group restoration")
    workspace.context.detach("p2")
    workspace.open({ id: "extra", title: "Extra", kind: "work" })
    const blank = defineComponent({ render: () => null })
    windows.open({ id: "form", look: { title: "Other form" }, size: { width: 300, height: 200 }, component: blank })
    await flushPromises()
    expect(await workspace.restore(saved)).toBe("restored")
    await flushPromises()
    expect(windows.context.windows.value.map((entry) => entry.id)).toEqual(["form"])
    expect(mayClose).toHaveBeenCalledWith("extra")
    expect(mayClose).not.toHaveBeenCalledWith("p2")
    expect(body.get('[data-testid="workspace-leaf-work"] input').element).toBe(input.element)
    expect((input.element as HTMLInputElement).value).toBe("kept across group restoration")
    expect(disposed).toHaveBeenCalledWith("extra")
    expect(disposed).not.toHaveBeenCalledWith("p2")
  })

  it("renames a panel in place, keeping the instance and what is half-written in it", async () => {
    // A console that somebody keeps becomes a document and is renamed for it.
    // Rebuilding the panel there would throw away the results in it and the
    // answer half typed into it, which is the opposite of what keeping means.
    const { workspace, body, mounted, disposed } = await fixture()
    const input = body.get('input[aria-label="Draft p2"]')
    await input.setValue("half-written")
    const built = mounted.mock.calls.length

    workspace.replace("p2", { id: "p9", title: "Orders, kept", kind: "work" })
    await flushPromises()

    const after = body.get('[data-testid="workspace-leaf-work"] input')
    expect(after.element).toBe(input.element)
    expect((after.element as HTMLInputElement).value).toBe("half-written")
    expect(mounted.mock.calls.length).toBe(built)
    expect(disposed).not.toHaveBeenCalledWith("p2")
    // Drawn from the object the engine kept, so the new name reaches the panel
    // rather than stopping at the tab above it.
    expect(after.attributes("data-panel-title")).toBe("Orders, kept")
    expect(body.find('[data-testid="workspace-tab-p9"]').exists()).toBe(true)
    expect(body.find('[data-testid="workspace-tab-p2"]').exists()).toBe(false)
  })

  it("retains the same input and page injections across detachment, minimization and return", async () => {
    const { workspace, body, mounted, disposed, deactivated } = await fixture()
    const input = body.get('input[aria-label="Draft p2"]')
    await input.setValue("unsaved editor state")
    expect(mounted).not.toHaveBeenCalledWith("p3")

    workspace.context.detach("p2")
    await flushPromises()
    const floating = body.get('[role="dialog"][aria-label="Orders"]')
    expect(floating.get('input[aria-label="Draft p2"]').element).toBe(input.element)
    expect(input.attributes("data-page-context")).toBe("kept")
    expect(body.find('[data-testid="workspace-tab-p2"]').exists()).toBe(false)
    expect(mounted).toHaveBeenCalledWith("p3")

    await body.get('[data-testid="workspace-leaf-work"]').trigger("pointerdown")
    expect(workspace.context.focusedDetached.value).toBeNull()
    await floating.trigger("pointerdown")
    expect(workspace.context.focusedDetached.value).toBe("p2")

    await floating.get('[aria-label="Minimize"]').trigger("click")
    await flushPromises()
    expect(body.find('input[aria-label="Draft p2"]').exists()).toBe(false)
    expect(deactivated).toHaveBeenCalledWith("p2")
    workspace.open({ id: "p2", title: "Orders", kind: "work" })
    await flushPromises()
    expect(body.findAll('[role="dialog"]')).toHaveLength(1)
    expect(floating.get('input[aria-label="Draft p2"]').element).toBe(input.element)
    // The way back is a command of the frame, beside minimize and close (D112).
    await floating.get('[data-testid="dock-panel"]').trigger("click")
    await flushPromises()
    expect(body.findAll('[role="dialog"]')).toHaveLength(0)
    expect(body.get('[data-testid="workspace-leaf-work"] input').element).toBe(input.element)
    expect((input.element as HTMLInputElement).value).toBe("unsaved editor state")
    expect(mounted.mock.calls.filter(([id]) => id === "p2")).toHaveLength(1)
    expect(disposed).not.toHaveBeenCalledWith("p2")
  })

  it("follows a panel title and replacement id and still asks before closing", async () => {
    const { workspace, body, mayClose, disposed } = await fixture()
    workspace.context.detach("p2")
    await flushPromises()
    workspace.replace("p2", { id: "saved", title: "Saved orders", kind: "work" })
    await flushPromises()
    expect(body.findAll('[role="dialog"]')).toHaveLength(1)
    const floating = body.get('[role="dialog"][aria-label="Saved orders"]')
    expect(floating.find('input[aria-label="Draft saved"]').exists()).toBe(true)
    mayClose.mockReturnValue(false)
    await floating.get('[aria-label="Close window"]').trigger("click")
    await flushPromises()
    expect(mayClose).toHaveBeenCalledWith("saved")
    expect(body.find('[role="dialog"]').exists()).toBe(true)
    mayClose.mockReturnValue(true)
    await floating.get('[aria-label="Close window"]').trigger("click")
    await flushPromises()
    expect(body.find('[role="dialog"]').exists()).toBe(false)
    expect(disposed).toHaveBeenCalledWith("saved")
  })

  it("cancels a drag outside the workspace on Escape and pointer cancellation", async () => {
    const { workspace, body } = await fixture()
    workspace.context.press("p2", 30, 60)
    window.dispatchEvent(new MouseEvent("pointermove", { clientX: 40, clientY: 10 }))
    await flushPromises()
    expect(body.find('[data-testid="workspace-detach-target"]').exists()).toBe(true)
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }))
    await flushPromises()
    expect(body.find('[data-testid="workspace-detach-target"]').exists()).toBe(false)
    expect(workspace.context.detached.value).toEqual([])
    workspace.context.press("p2", 30, 60)
    window.dispatchEvent(new Event("pointercancel"))
    window.dispatchEvent(new MouseEvent("pointermove", { clientX: 50, clientY: 10 }))
    expect(workspace.context.dragging.value).toBeNull()
  })

  it("cleans up detached windows on reset without closing unrelated windows", async () => {
    const { workspace, windows, body } = await fixture()
    const blank = defineComponent({ render: () => null })
    windows.open({ id: "form", look: { title: "Other form" }, size: { width: 300, height: 200 }, component: blank })
    workspace.context.detach("p2")
    workspace.context.detach("p3")
    await flushPromises()
    expect(body.findAll('[role="dialog"]')).toHaveLength(3)
    workspace.reset()
    await flushPromises()
    expect(windows.context.windows.value.map((entry) => entry.id)).toEqual(["form"])
  })
})
