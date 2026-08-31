import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { AxiosError } from "axios"
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
  takesManyFiles: false,
  previews: true,
  downloads: false,
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

const RENAME: ActionCommand = {
  name: "rename",
  label: "Rename",
  destructive: false,
  takesFile: false,
  takesManyFiles: false,
  previews: false,
  downloads: false,
  actsOn: "node",
  fields: [
    {
      name: "new_name",
      label: "New name",
      kind: "text",
      required: true,
      purpose: "node-name",
      group: "general",
    },
  ],
}

const UPLOAD: ActionCommand = {
  name: "upload",
  label: "Upload files",
  destructive: false,
  takesFile: true,
  takesManyFiles: true,
  previews: false,
  downloads: false,
  actsOn: "children",
  fields: [
    {
      name: "conflict",
      label: "File conflict",
      kind: "hidden",
      required: false,
      defaultValue: "refuse",
      purpose: "file-conflict",
      group: "general",
    },
  ],
}

function mountDialog(
  command: ActionCommand = DROP,
  nodeIds: (string | null)[] = ["demo.customers"],
  targetNode?: { label: string; kind: string }
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(
    withWindowHost(ActionDialog, {
      command,
      connectorId: "c-1",
      nodeIds,
      nodeLabel: "customers",
      targetNode,
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

function click(testid: string): void {
  document.body.querySelector<HTMLElement>(`[data-testid="${testid}"]`)?.click()
}

/**
 * What the picker hands back once the user has chosen.
 *
 * By name rather than by the component itself: the file field is generic
 * over the shape of its value, and a generic component reaches this call as
 * a functional one, whose wrapper has no instance to emit from.
 */
function choose(
  wrapper: ReturnType<typeof mountDialog>,
  chosen: File[]
): void {
  wrapper
    .findComponent({ name: "AppFileInput" })
    .vm.$emit("update:modelValue", chosen)
}

function csv(name: string): File {
  return new File(["id"], name, { type: "text/csv" })
}

function refused(status: number): AxiosError {
  return new AxiosError("refused", undefined, undefined, undefined, {
    status,
  } as never)
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
  it("asks a plain destructive question that names the target", async () => {
    const wrapper = mountDialog(DROP, ["demo.customers"], {
      label: "customers",
      kind: "table",
    })
    await flushPromises()

    expect(text("action-confirmation")).toContain(
      "Are you sure you want to delete customers?"
    )
    expect(document.body.querySelector('[data-testid="action-warning"]')).toBeNull()
    wrapper.unmount()
  })

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

describe("renaming a file", () => {
  it("starts with the current name selected without its extension", async () => {
    const wrapper = mountDialog(RENAME, ["reports/uploaded.csv"], {
      label: "uploaded.csv",
      kind: "file",
    })
    await flushPromises()

    const input = document.body.querySelector<HTMLInputElement>(
      '[data-testid="field-new_name"]'
    )
    expect(input?.value).toBe("uploaded")
    wrapper.unmount()
  })

  it("keeps the old extension when no new extension is typed", async () => {
    const run = vi.spyOn(ConnectorsService, "runAction").mockResolvedValue({
      data: { message: "renamed", reload_node_ids: ["reports"] },
    } as never)
    const wrapper = mountDialog(RENAME, ["reports/uploaded.csv"], {
      label: "uploaded.csv",
      kind: "file",
    })
    await flushPromises()

    const input = document.body.querySelector<HTMLInputElement>(
      '[data-testid="field-new_name"]'
    )
    if (input === null) throw new Error("Rename field did not render")
    input.value = "renamed"
    input.dispatchEvent(new Event("input", { bubbles: true }))
    document.body.querySelector<HTMLElement>('[data-testid="action-submit"]')?.click()
    await flushPromises()

    expect(run).toHaveBeenCalledWith({
      path: { connector_id: "c-1", action_name: "rename" },
      body: {
        node_id: "reports/uploaded.csv",
        params: { new_name: "renamed.csv" },
      },
    })
    wrapper.unmount()
  })
})

describe("renaming a database relation", () => {
  it("starts with the current relation name", async () => {
    const wrapper = mountDialog(RENAME, ["demo.customers"], {
      label: "customers",
      kind: "table",
    })
    await flushPromises()

    const input = document.body.querySelector<HTMLInputElement>(
      '[data-testid="field-new_name"]'
    )
    expect(input?.value).toBe("customers")
    wrapper.unmount()
  })
})

describe("uploading files", () => {
  it("stages what was chosen and sends nothing until it is asked to", async () => {
    // The whole reason the list exists: a picker that uploaded on its own
    // would leave nothing to correct.
    const upload = vi.spyOn(ConnectorsService, "runActionWithFile")
    const wrapper = mountDialog(UPLOAD, [null])
    await flushPromises()

    choose(wrapper, [csv("first.csv"), csv("second.csv")])
    await flushPromises()

    expect(upload).not.toHaveBeenCalled()
    expect(text("action-files")).toContain("first.csv")
    expect(text("action-files")).toContain("second.csv")
    wrapper.unmount()
  })

  it("does not send a file that was taken off the list", async () => {
    const upload = vi.spyOn(ConnectorsService, "runActionWithFile").mockResolvedValue({
      data: { message: "second.csv uploaded", reload_node_ids: [null] },
    } as never)
    const wrapper = mountDialog(UPLOAD, [null])
    await flushPromises()

    const kept = csv("second.csv")
    choose(wrapper, [csv("first.csv"), kept])
    await flushPromises()
    click("action-file-remove-0")
    await flushPromises()
    click("action-submit")
    await flushPromises()

    expect(upload).toHaveBeenCalledTimes(1)
    expect(upload).toHaveBeenCalledWith({
      path: { connector_id: "c-1", action_name: "upload" },
      body: {
        file: kept,
        node_id: "",
        params: JSON.stringify({ conflict: "refuse" }),
      },
    })
    wrapper.unmount()
  })

  it("sends one request per file, and one refusal does not stop the rest", async () => {
    const upload = vi
      .spyOn(ConnectorsService, "runActionWithFile")
      .mockResolvedValueOnce({
        data: { message: "first.csv uploaded", reload_node_ids: [null] },
      } as never)
      .mockRejectedValueOnce(refused(409))
      .mockResolvedValueOnce({
        data: { message: "second (1).csv uploaded", reload_node_ids: [null] },
      } as never)
    const wrapper = mountDialog(UPLOAD, [null])
    await flushPromises()

    const taken = csv("second.csv")
    choose(wrapper, [csv("first.csv"), taken])
    await flushPromises()
    click("action-submit")
    await flushPromises()

    // What landed is gone from the list; what was refused stays there, which
    // is where the answer to it is.
    expect(upload).toHaveBeenCalledTimes(2)
    expect(text("action-files")).toContain("second.csv")
    expect(text("action-files")).not.toContain("first.csv")
    expect(text("action-error")).toContain("second.csv already exists")

    click("action-keep-both")
    await flushPromises()

    expect(upload).toHaveBeenCalledTimes(3)
    expect(upload).toHaveBeenLastCalledWith({
      path: { connector_id: "c-1", action_name: "upload" },
      body: {
        file: taken,
        node_id: "",
        params: JSON.stringify({ conflict: "rename" }),
      },
    })
    wrapper.unmount()
  })

  it("asks about a conflict only after the file has been chosen", async () => {
    const upload = vi
      .spyOn(ConnectorsService, "runActionWithFile")
      .mockRejectedValueOnce(refused(409))
      .mockResolvedValueOnce({
        data: { message: "report (1).csv uploaded", reload_node_ids: [null] },
      } as never)
    const wrapper = mountDialog(UPLOAD, [null])
    await flushPromises()

    const file = csv("report.csv")
    choose(wrapper, [file])
    await flushPromises()

    // Nothing has been asked yet, so there is nothing to be in conflict with.
    expect(document.body.querySelector('[data-testid="action-keep-both"]')).toBeNull()
    click("action-submit")
    await flushPromises()

    expect(document.body.querySelector('[data-testid="action-keep-both"]')).not.toBeNull()
    click("action-keep-both")
    await flushPromises()

    expect(upload).toHaveBeenLastCalledWith({
      path: { connector_id: "c-1", action_name: "upload" },
      body: {
        file,
        node_id: "",
        params: JSON.stringify({ conflict: "rename" }),
      },
    })
    wrapper.unmount()
  })
})
