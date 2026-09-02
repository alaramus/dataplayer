import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import type { UnlockState } from "@/client"

import WriteMode from "./WriteMode.vue"

type Mode = "read" | "auto_commit" | "manual"

const UNLOCKED: UnlockState = {
  connector_id: "c1",
  policy: "confirm_writes",
  access: "structure",
  unlocked: false,
}

function open(modes: Mode[], unlock: UnlockState | undefined = UNLOCKED) {
  return mount(WriteMode, {
    props: {
      mode: "read" as Mode,
      modes,
      unlock,
      connectorLabel: "local pg",
      busy: false,
    },
    global: { plugins: [Quasar] },
  })
}

describe("choosing what a console may do", () => {
  it("offers the modes the source published", () => {
    const wrapper = open(["read", "auto_commit", "manual"])

    expect(wrapper.find('[data-testid="query-mode"]').exists()).toBe(true)
  })

  it("draws nothing for a source that only reads", () => {
    // The file source runs SQL over files and changes none of them (D77), so
    // its profile offers one mode — and one option is not a choice.
    const wrapper = open(["read"])

    expect(wrapper.find('[data-testid="query-mode"]').exists()).toBe(false)
    expect(wrapper.text()).toBe("")
  })
})
