<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { serverCheckOptions } from "./api"
import { switchServer } from "@/shared/servers/leaving"
import { normalizeServerUrl, parseProfile, safeLocalPath } from "@/shared/servers/profiles"
import AppActions from "@/shared/ui/AppActions.vue"
import AppBanner from "@/shared/ui/AppBanner.vue"
import AppButton from "@/shared/ui/AppButton.vue"
import AppCard from "@/shared/ui/AppCard.vue"
import AppInput from "@/shared/ui/AppInput.vue"
import AppSection from "@/shared/ui/AppSection.vue"
import { useServersStore } from "@/stores/servers"

const route = useRoute()
const router = useRouter()
const servers = useServersStore()
const cache = useQueryClient()
const name = ref("")
const address = ref("")
const error = ref("")
const busy = ref(false)

watch(() => route.query.server, (value) => {
  address.value = typeof value === "string" ? value : ""
  const known = servers.profiles.find((profile) => profile.url === address.value)
  try { name.value = known?.name ?? new URL(address.value).host }
  catch { name.value = "New server" }
  error.value = ""
}, { immediate: true })

async function connect() {
  if (busy.value) return
  busy.value = true
  error.value = ""
  try {
    const url = normalizeServerUrl(address.value)
    const profile = parseProfile({ name: name.value, url })
    if (profile === null) throw new Error("Enter a server name of 1 to 100 characters.")
    await cache.fetchQuery({ ...serverCheckOptions(url), staleTime: 0 })
    const next = safeLocalPath(route.query.next) ?? "/"
    await switchServer(url, next, () => {
      if (!servers.profiles.some((item) => item.url === url)) servers.save(profile)
    })
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : "Could not connect to this server."
  } finally { busy.value = false }
}
</script>

<template>
  <div class="server-connect">
    <AppCard
      size="sm"
      title="Choose the server for this link"
    >
      <AppSection gutter>
        <AppBanner tone="info">
          This link uses another server. Check the address before connecting; you may need to sign in there.
        </AppBanner>
        <AppInput
          v-model="name"
          label="Server name"
          :disable="busy"
          maxlength="100"
        />
        <AppInput
          v-model="address"
          label="Server URL"
          :disable="busy"
          data-testid="link-server-url"
        />
        <AppBanner
          v-if="error"
          tone="error"
        >
          {{ error }}
        </AppBanner>
      </AppSection>
      <AppActions>
        <AppButton
          label="Cancel"
          variant="quiet"
          :disable="busy"
          @click="router.push('/')"
        />
        <AppButton
          label="Check and connect"
          :loading="busy"
          data-testid="link-server-connect"
          @click="connect"
        />
      </AppActions>
    </AppCard>
  </div>
</template>

<style scoped>
.server-connect { min-height: 100vh; display: grid; place-items: center; padding: 16px; }
</style>
