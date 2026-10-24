import { flushPromises, mount } from "@vue/test-utils"
import { QSelect, Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"
import { defineComponent, Fragment, h, nextTick, ref } from "vue"

import type { AdapterTypeInfo } from "@/client"
import { provideWindows, useWindows, WindowHost } from "@/shared/windows"

import MakeHereDialog from "./MakeHereDialog.vue"

const SQLITE = { name: "sqlite", title: "SQLite", makes_here: true } as AdapterTypeInfo

/** The dialog behind the page's `v-model:type`, which clears the type on close. */
async function openDialog() {
  const made: unknown[] = []
  const type = ref<AdapterTypeInfo | null>(null)
  const Root = defineComponent({
    setup() {
      const windows = useWindows()
      provideWindows(windows)
      return () =>
        h(Fragment, [
          h(MakeHereDialog, {
            type: type.value,
            "onUpdate:type": (value: AdapterTypeInfo | null) => {
              type.value = value
            },
            onMake: (payload: unknown) => made.push(payload),
          }),
          h(WindowHost, { context: windows.context }),
        ])
    },
  })
  const wrapper = mount(Root, { global: { plugins: [Quasar] } })
  // Opened after mounting, as the page does: the form starts over on a type.
  type.value = SQLITE
  await nextTick()
  await flushPromises()
  return { wrapper, made }
}

function field(testId: string): HTMLInputElement {
  const found = document.body.querySelector<HTMLInputElement>(`[data-testid="${testId}"]`)
  if (found === null) throw new Error(`no ${testId}`)
  return found
}

function type(testId: string, value: string) {
  const input = field(testId)
  input.value = value
  input.dispatchEvent(new Event("input"))
}

function submit() {
  document.body.querySelector<HTMLButtonElement>('[data-testid="make-here-submit"]')?.click()
}

describe("a database made here (D263)", () => {
  it("asks nothing when left to the server, and sends no choice", async () => {
    const { wrapper, made } = await openDialog()

    expect(document.body.querySelector('[data-testid="make-here-automatic-summary"]')?.textContent)
      .toContain("databases/dataplayer.db")
    expect(document.body.querySelector('[data-testid="make-here-name"]')).toBeNull()
    submit()
    await flushPromises()

    expect(made).toEqual([{ adapterType: "sqlite", choice: {} }])
    expect(document.body.querySelector('[data-testid="make-here-dialog"]')).toBeNull()
    wrapper.unmount()
  })

  it("sends what was chosen, and leaves out what was not", async () => {
    const { wrapper, made } = await openDialog()
    ;(wrapper.getComponent(QSelect).vm as unknown as { showPopup: () => void }).showPopup()
    await vi.waitFor(() => {
      expect(document.body.querySelector('[role="option"]')).not.toBeNull()
    })
    const chosen = [...document.body.querySelectorAll<HTMLElement>('[role="option"]')]
      .find((option) => option.textContent?.includes("Let me choose"))
    chosen?.click()
    await flushPromises()

    type("make-here-name", "  Sales  ")
    field("make-here-wal").click()
    await flushPromises()
    submit()
    await flushPromises()

    expect(made).toEqual([
      { adapterType: "sqlite", choice: { name: "Sales", folder: null, sample_data: true, wal: true } },
    ])
    wrapper.unmount()
  })
})
