import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"

import { copyText } from "@/shared/clipboard"

import ConnectionCheck from "./ConnectionCheck.vue"

vi.mock("@/shared/clipboard", () => ({ copyText: vi.fn().mockResolvedValue(undefined) }))
vi.mock("@/shared/ui/useToast", () => ({ useToast: () => ({ success: vi.fn() }) }))

describe("connection check result", () => {
  it("keeps failure details, the recovery action, copy and dismissal available", async () => {
    const wrapper = mount(ConnectionCheck, {
      global: { plugins: [Quasar] },
      props: {
        sourceTitle: "PostgreSQL",
        result: { ok: false, message: "Unlock the SSH key to continue", error_kind: "locked", latency_ms: 0 },
      },
      slots: { action: '<button>Unlock the key</button>' },
    })
    expect(wrapper.get('[role="status"]').text()).toBe("Failed")
    expect(wrapper.text()).toContain("Key locked")
    expect(wrapper.text()).toContain("Unlock the key")
    await wrapper.get('[data-testid="copy-check-result"]').trigger("click")
    expect(copyText).toHaveBeenCalledWith("Failed\nKey locked\nUnlock the SSH key to continue\nPing: 0 ms")
    await wrapper.get('[data-testid="dismiss-check-result"]').trigger("click")
    expect(wrapper.emitted("close")).toHaveLength(1)
    await wrapper.setProps({ result: null })
    expect(wrapper.find('[data-testid="check-result"]').exists()).toBe(false)
  })
})
