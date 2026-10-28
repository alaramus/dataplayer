import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { defineComponent, h, nextTick, ref } from "vue"
import type { PropType } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import type { GrantPublic } from "@/client"
import { useGrants } from "@/features/connectors/grants"

import GrantList from "./GrantList.vue"

const CONNECTOR = "connector-1"

/**
 * What the server holds, as the two requests see it: the list, and the
 * deletion that changes it. A refetch after the deletion must answer with
 * what is left, which is the whole question the list has to get right.
 */
let held: GrantPublic[] = []

function grant(user_id: string, email: string): GrantPublic {
  return { user_id, email, full_name: null, access: "read" } as GrantPublic
}

function mountList() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(GrantList, {
    props: { connectorId: CONNECTOR },
    global: {
      plugins: [
        [Quasar, { plugins: { Dialog, Notify } }],
        [VueQueryPlugin, { queryClient }],
      ],
    },
  })
}

/**
 * The second place that reads one connection's grants, as the Share dialog
 * does: it opens on the connection the list is on, so it files itself under the
 * list's key and then leaves it again when the dialog closes.
 *
 * A cache entry keeps the query function of whoever filed it last, so the
 * refetch a revocation asks for can end up being this one's — reading a
 * connection it no longer has.
 */
const Sharer = defineComponent({
  props: {
    connectorId: { type: String as PropType<string | null>, default: null },
  },
  setup(props) {
    useGrants(() => props.connectorId)
    return () => h("div")
  },
})

const openedOn = ref<string | null>(CONNECTOR)

function mountBoth() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  const Harness = defineComponent({
    setup() {
      return () =>
        h("div", [
          h(GrantList, { connectorId: CONNECTOR }),
          h(Sharer, { connectorId: openedOn.value }),
        ])
    },
  })
  return mount(Harness, {
    global: {
      plugins: [
        [Quasar, { plugins: { Dialog, Notify } }],
        [VueQueryPlugin, { queryClient }],
      ],
    },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  held = [grant("user-1", "first@example.com"), grant("user-2", "second@example.com")]
  vi.spyOn(ConnectorsService, "readGrants").mockImplementation(
    async () => ({ data: { data: [...held] } }) as never
  )
  vi.spyOn(ConnectorsService, "revokeGrant").mockImplementation(async ({ path }) => {
    held = held.filter((row) => row.user_id !== path.user_id)
    return { data: { message: "Access revoked" } } as never
  })
})
describe("the people a connection is shared with", () => {
  it("drops the row of somebody the level was taken from", async () => {
    const wrapper = mountList()
    await flushPromises()

    expect(wrapper.findAll('[data-testid^="share-row-"]')).toHaveLength(2)

    await wrapper.get('[data-testid="share-revoke-first@example.com"]').trigger("click")
    await flushPromises()

    expect(wrapper.findAll('[data-testid^="share-row-"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="share-row-second@example.com"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it("says nobody is here once the last level is taken back", async () => {
    held = [grant("user-1", "first@example.com")]
    const wrapper = mountList()
    await flushPromises()

    await wrapper.get('[data-testid="share-revoke-first@example.com"]').trigger("click")
    await flushPromises()

    expect(wrapper.findAll('[data-testid^="share-row-"]')).toHaveLength(0)
    wrapper.unmount()
  })

  it("asks about the connection its entry was filed under, not about one a closed dialog left behind", async () => {
    openedOn.value = CONNECTOR
    const asked: (string | null | undefined)[] = []
    vi.spyOn(ConnectorsService, "readGrants").mockImplementation(async ({ path }) => {
      asked.push(path?.connector_id)
      return { data: { data: [...held] } } as never
    })

    const wrapper = mountBoth()
    await flushPromises()
    expect(wrapper.findAll('[data-testid^="share-row-"]')).toHaveLength(2)

    // The dialog closes: the same cache entry, one tenant fewer.
    openedOn.value = null
    await nextTick()
    await flushPromises()

    await wrapper.get('[data-testid="share-revoke-first@example.com"]').trigger("click")
    await flushPromises()

    expect(asked.at(-1)).toBe(CONNECTOR)
    expect(wrapper.findAll('[data-testid^="share-row-"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="share-row-second@example.com"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
