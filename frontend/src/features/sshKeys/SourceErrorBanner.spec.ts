import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Notify, Quasar } from "quasar"
import { afterEach, describe, expect, it, vi } from "vitest"
import { defineComponent, Fragment, h } from "vue"

import { SshKeysService } from "@/client"
import type { SshKeyPublic } from "@/client"
import { provideWindows, useWindows, WindowHost } from "@/shared/windows"

import SourceErrorBanner from "./SourceErrorBanner.vue"

const KEY: SshKeyPublic = {
  id: "key-1",
  name: "deploy",
  algorithm: "ssh-ed25519",
  public_key: "ssh-ed25519 AAAA dataplayer",
  fingerprint: "SHA256:abc",
  passphrase_mode: "ask",
  unlocked_until: null,
  created_at: null,
  used_by: [{ id: "server-1", name: "Server" }],
}

function banner(connectorId: string, errorKind: string | null) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  // The window the button opens needs a host; the message is the banner's own
  // slot, which a generic host would not pass on.
  const Host = defineComponent({
    setup: () => {
      const windows = useWindows()
      provideWindows(windows)
      return () =>
        h(Fragment, [
          h(
            SourceErrorBanner,
            { connectorId, errorKind, "data-testid": "content-error" },
            { default: () => "The SSH key deploy is locked" }
          ),
          h(WindowHost, { context: windows.context }),
        ])
    },
  })
  return mount(
    Host,
    {
      global: {
        plugins: [
          [Quasar, { plugins: { Notify } }],
          [VueQueryPlugin, { queryClient }],
        ],
      },
    }
  )
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe("a source's failure, and the way on from it (D147)", () => {
  it("offers to unlock the key the connection signs in with when it is locked", async () => {
    vi.spyOn(SshKeysService, "keysReadSshKeys").mockResolvedValue({ data: [KEY] } as never)

    const wrapper = banner("server-1", "locked")
    await flushPromises()

    expect(wrapper.get('[data-testid="content-error"]').text()).toContain("is locked")
    await wrapper.get('[data-testid="unlock-key"]').trigger("click")
    await flushPromises()
    expect(document.body.querySelector('[data-testid="unlock-key-dialog"]')).not.toBeNull()
    wrapper.unmount()
  })

  it("asks for no keys and offers nothing when the failure is anything else", async () => {
    const read = vi.spyOn(SshKeysService, "keysReadSshKeys")

    const wrapper = banner("server-1", "network")
    await flushPromises()

    expect(wrapper.find('[data-testid="unlock-key"]').exists()).toBe(false)
    expect(read).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it("offers nothing to somebody whose own keys this connection does not use", async () => {
    // A grantee's list holds only their keys: the owner's is not in it.
    vi.spyOn(SshKeysService, "keysReadSshKeys").mockResolvedValue({ data: [KEY] } as never)

    const wrapper = banner("shared-server", "locked")
    await flushPromises()

    expect(wrapper.get('[data-testid="content-error"]').text()).toContain("is locked")
    expect(wrapper.find('[data-testid="unlock-key"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
