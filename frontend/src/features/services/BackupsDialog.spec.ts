import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"
import { ref } from "vue"

import { withWindowHost } from "@/shared/testing/windows"

import BackupsDialog from "./BackupsDialog.vue"

vi.mock("./api", () => ({
  useBackupOffer: () => ({
    data: ref({ available: false, reason: "TimescaleDB backup and restore are not supported" }),
    isError: ref(false), isFetching: ref(false), error: ref(null),
  }),
  useBackups: () => ({
    data: ref([{ filename: "old.dump", size_bytes: 100, modified_at: 1 }]),
    isLoading: ref(false),
  }),
  useBackUp: () => ({ mutateAsync: vi.fn() }),
  useRestore: () => ({ mutateAsync: vi.fn() }),
  useDeleteBackup: () => ({ mutateAsync: vi.fn() }),
}))

describe("source backup availability", () => {
  it("disables both operations with the source reason and retains file deletion", async () => {
    const wrapper = mount(withWindowHost(BackupsDialog, {
      connector: { id: "timescale", name: "Metrics" },
    }), { global: { plugins: [[Quasar, { plugins: { Dialog, Notify } }]] } })
    await flushPromises()
    expect(document.body.textContent).toContain("TimescaleDB backup and restore are not supported")
    expect(document.body.querySelector<HTMLButtonElement>('[data-testid="take-backup"]')?.disabled).toBe(true)
    expect(document.body.querySelector<HTMLButtonElement>('[data-testid="restore-old.dump"]')?.disabled).toBe(true)
    expect(document.body.querySelector<HTMLButtonElement>('[data-testid="delete-backup-old.dump"]')?.disabled).toBe(false)
    wrapper.unmount()
  })
})
