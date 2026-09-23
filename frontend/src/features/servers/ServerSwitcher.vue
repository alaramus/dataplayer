<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { computed, ref } from "vue"
import { useRoute } from "vue-router"

import { serverCheckOptions } from "@/features/servers/api"
import { switchServer } from "@/shared/servers/leaving"
import { normalizeServerUrl, parseProfile, safeLocalPath } from "@/shared/servers/profiles"
import type { ServerProfile } from "@/shared/servers/profiles"
import AppBanner from "@/shared/ui/AppBanner.vue"
import AppButton from "@/shared/ui/AppButton.vue"
import AppForm from "@/shared/ui/AppForm.vue"
import AppIconButton from "@/shared/ui/AppIconButton.vue"
import AppInput from "@/shared/ui/AppInput.vue"
import AppTooltip from "@/shared/ui/AppTooltip.vue"
import { WindowDialog } from "@/shared/windows"
import { useServersStore } from "@/stores/servers"

const servers = useServersStore()

/** Icon-only rendering for the footer, in line with the rail buttons. */
withDefaults(defineProps<{ iconOnly?: boolean }>(), { iconOnly: false })

const cache = useQueryClient()
const route = useRoute()
const open = ref(false)
const editing = ref(false)
const previousUrl = ref<string | undefined>()
const name = ref("")
const address = ref("")
const error = ref("")
const notice = ref("")
const busy = ref(false)
const savingActiveAddress = computed(() => previousUrl.value === servers.active.url && address.value.trim().replace(/\/+$/, "") !== servers.active.url)

function edit(profile?: ServerProfile) {
  previousUrl.value = profile?.url
  name.value = profile?.name ?? ""
  address.value = profile?.url ?? ""
  editing.value = true
  error.value = ""
  notice.value = ""
}

async function perform(action: () => void | Promise<void>) {
  if (busy.value) return
  busy.value = true
  error.value = ""
  notice.value = ""
  try { await action() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "Could not save the server in this browser." }
  finally { busy.value = false }
}

async function check(url: string) {
  await cache.fetchQuery({ ...serverCheckOptions(url), staleTime: 0 })
}

function checkForm() {
  void perform(async () => {
    await check(normalizeServerUrl(address.value))
    notice.value = "Compatible DataPlayer server."
  })
}

function nextPath(): string {
  return route.name === "login" ? safeLocalPath(route.query.next) ?? "/" : "/"
}

function connect(profile: ServerProfile) {
  void perform(async () => {
    await check(profile.url)
    if (profile.url === servers.active.url) {
      notice.value = "Compatible DataPlayer server."
      return
    }
    await switchServer(profile.url, nextPath())
  })
}

function save() {
  void perform(async () => {
    const url = normalizeServerUrl(address.value)
    const profile = parseProfile({ name: name.value, url })
    if (profile === null) throw new Error("Enter a server name of 1 to 100 characters.")
    if (previousUrl.value === servers.active.url && url !== servers.active.url) {
      await check(url)
      await switchServer(url, nextPath(), () => servers.save(profile, previousUrl.value))
      return
    }
    servers.save(profile, previousUrl.value)
    editing.value = false
    notice.value = "Server saved. Choose Connect to use it in this tab."
  })
}

function remove(profile: ServerProfile) {
  void perform(async () => {
    if (profile.url === servers.active.url) {
      await check(servers.defaultServer.url)
      await switchServer(servers.defaultServer.url, "/", () => servers.remove(profile.url))
    } else servers.remove(profile.url)
  })
}
</script>

<template>
  <AppButton
    variant="quiet"
    size="sm"
    icon="vpn_lock"
    class="server-switcher"
    aria-label="Choose server"
    data-testid="server-switcher"
    @click="open = true; editing = false; error = ''; notice = ''"
  >
    <span
      v-if="!iconOnly"
      class="server-switcher__name"
    >{{ servers.active.name }}</span>
    <AppTooltip>{{ servers.active.url }}</AppTooltip>
  </AppButton>
  <WindowDialog
    v-model="open"
    title="Servers"
    subtitle="Choose the server for this browser tab. Accounts are separate on each server."
    size="form"
    sizing="stable"
    data-testid="server-manager"
  >
    <AppForm layout="section">
      <div class="server-switcher__current">
        Current: {{ servers.active.name }} · {{ servers.active.url }}
      </div>
      <template v-if="editing">
        <AppInput
          v-model="name"
          label="Server name"
          :disable="busy"
          data-testid="server-name"
          maxlength="100"
        />
        <AppInput
          v-model="address"
          label="Server URL"
          placeholder="https://data.example.com"
          :disable="busy"
          data-testid="server-url"
        />
      </template>
      <template v-else>
        <div
          v-for="profile in servers.profiles"
          :key="profile.url"
          class="server-switcher__row"
          data-testid="server-profile"
        >
          <div class="server-switcher__details">
            <strong>{{ profile.name }}</strong>
            <span v-if="profile.url === servers.active.url"> · Current</span>
            <div class="server-switcher__url">
              {{ profile.url }}
            </div>
          </div>
          <AppButton
            :label="profile.url === servers.active.url ? 'Check' : 'Connect'"
            variant="quiet"
            size="sm"
            :disable="busy"
            @click="connect(profile)"
          />
          <template v-if="profile.url !== servers.defaultServer.url">
            <AppIconButton
              icon="edit"
              tooltip="Edit server"
              aria-label="Edit server"
              :disable="busy"
              @click="edit(profile)"
            />
            <AppIconButton
              icon="delete"
              tooltip="Remove server"
              aria-label="Remove server"
              variant="danger-quiet"
              :disable="busy"
              @click="remove(profile)"
            />
          </template>
        </div>
        <div>
          <AppButton
            label="Add server"
            icon="add"
            variant="secondary"
            :disable="busy"
            data-testid="server-add"
            @click="edit()"
          />
        </div>
      </template>
    </AppForm>

    <template #actions>
      <div
        v-if="error || notice"
        class="server-switcher__strip"
      >
        <AppBanner
          v-if="error"
          tone="error"
          data-testid="server-error"
        >
          {{ error }}
        </AppBanner>
        <AppBanner
          v-if="notice"
          tone="info"
          data-testid="server-notice"
        >
          {{ notice }}
        </AppBanner>
      </div>
      <template v-if="editing">
        <AppButton
          label="Check connection"
          variant="secondary"
          :disable="busy"
          @click="checkForm"
        />
        <AppButton
          :label="savingActiveAddress ? 'Save and connect' : 'Save server'"
          :loading="busy"
          data-testid="server-save"
          @click="save"
        />
        <AppButton
          label="Cancel"
          variant="quiet"
          :disable="busy"
          @click="editing = false; error = ''; notice = ''"
        />
      </template>
      <AppButton
        v-else
        label="Close"
        variant="quiet"
        @click="open = false"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.server-switcher { flex: none; max-width: min(240px, 38vw); }
.server-switcher__name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 170px; }
.server-switcher__row { display: flex; align-items: center; gap: var(--dp-space-1); padding: var(--dp-space-2) 0; border-bottom: 1px solid var(--dp-border); }
.server-switcher__details { flex: 1; min-width: 0; }
.server-switcher__url, .server-switcher__current { color: var(--dp-text-muted); font-size: 12px; overflow-wrap: anywhere; }
.server-switcher__strip { flex-basis: 100%; display: flex; flex-direction: column; gap: var(--dp-space-2); }
</style>
