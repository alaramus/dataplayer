import { defineStore } from "pinia"
import { computed, onScopeDispose, ref } from "vue"

import { t } from "@/shared/i18n"
import { serverContext } from "@/shared/servers/context"
import { PROFILES_KEY, parseProfile, parseProfiles } from "@/shared/servers/profiles"
import type { ServerProfile } from "@/shared/servers/profiles"

export const useServersStore = defineStore("servers", () => {
  const context = serverContext()
  const saved = ref<ServerProfile[]>([])
  function load() {
    try { saved.value = parseProfiles(localStorage.getItem(PROFILES_KEY)) } catch { saved.value = [] }
  }
  load()
  const profiles = computed(() => [
    context.defaultServer,
    ...saved.value.filter((profile) => profile.url !== context.defaultServer.url),
  ])
  const active = computed(() => profiles.value.find((profile) => profile.url === context.active.url) ?? context.active)
  function write(next: ServerProfile[]) {
    localStorage.setItem(PROFILES_KEY, JSON.stringify(next))
    saved.value = next
  }
  function save(profile: ServerProfile, previousUrl?: string) {
    const parsed = parseProfile(profile)
    if (parsed === null) throw new Error(t("shell.servers.invalid_profile"))
    profile = parsed
    if (profile.url === context.defaultServer.url) throw new Error(t("shell.servers.default_is_configured"))
    if (saved.value.some((item) => item.url === profile.url && item.url !== previousUrl)) {
      throw new Error(t("shell.servers.already_saved"))
    }
    if (!saved.value.some((item) => item.url === previousUrl) && saved.value.length >= 50) {
      throw new Error(t("shell.servers.too_many", { n: 50 }))
    }
    write([...saved.value.filter((item) => item.url !== previousUrl), profile])
  }
  function remove(url: string) {
    write(saved.value.filter((profile) => profile.url !== url))
  }
  function changed(event: StorageEvent) {
    if (event.key === null || event.key === PROFILES_KEY) load()
  }
  window.addEventListener("storage", changed)
  onScopeDispose(() => window.removeEventListener("storage", changed))
  return { profiles, active, save, remove, defaultServer: context.defaultServer }
})
