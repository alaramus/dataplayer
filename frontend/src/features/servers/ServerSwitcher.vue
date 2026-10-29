<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { useQueryClient } from "@tanstack/vue-query"
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { useRoute } from "vue-router"

import { serverCheckOptions } from "@/features/servers/api"
import { t } from "@/shared/i18n"
import { switchServer } from "@/shared/servers/leaving"
import { normalizeServerUrl, parseProfile, safeLocalPath } from "@/shared/servers/profiles"
import type { ServerProfile } from "@/shared/servers/profiles"
import AppBanner from "@/shared/ui/AppBanner.vue"
import AppButton from "@/shared/ui/AppButton.vue"
import AppForm from "@/shared/ui/AppForm.vue"
import AppIconButton from "@/shared/ui/AppIconButton.vue"
import AppInput from "@/shared/ui/AppInput.vue"
import AppTooltip from "@/shared/ui/AppTooltip.vue"
import { useWindowManager } from "@/shared/windows"
import { useServersStore } from "@/stores/servers"

const servers = useServersStore()
const windows = useWindowManager()

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

function onKey(event: KeyboardEvent) {
  if (event.key === "Escape" && open.value) open.value = false
}
onMounted(() => window.addEventListener("keydown", onKey))
onBeforeUnmount(() => window.removeEventListener("keydown", onKey))

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
  catch (cause) { error.value = cause instanceof Error ? cause.message : t("servers.switcher.save_failed") }
  finally { busy.value = false }
}

async function check(url: string) {
  await cache.fetchQuery({ ...serverCheckOptions(url), staleTime: 0 })
}

function checkForm() {
  void perform(async () => {
    await check(normalizeServerUrl(address.value))
    notice.value = t("servers.switcher.compatible")
  })
}

function nextPath(): string {
  return route.name === "login" ? safeLocalPath(route.query.next) ?? "/" : "/"
}

function connect(profile: ServerProfile) {
  void perform(async () => {
    await check(profile.url)
    if (profile.url === servers.active.url) {
      notice.value = t("servers.switcher.compatible")
      return
    }
    await switchServer(profile.url, nextPath())
  })
}

function save() {
  void perform(async () => {
    const url = normalizeServerUrl(address.value)
    const profile = parseProfile({ name: name.value, url })
    if (profile === null) throw new Error(t("servers.name_invalid"))
    if (previousUrl.value === servers.active.url && url !== servers.active.url) {
      await check(url)
      await switchServer(url, nextPath(), () => servers.save(profile, previousUrl.value))
      return
    }
    servers.save(profile, previousUrl.value)
    editing.value = false
    notice.value = t("servers.switcher.saved")
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
    layout="toolbar"
    :icon="appIcons.vpnLock"
    class="server-switcher"
    :aria-label="t('servers.switcher.choose')"
    data-testid="server-switcher"
    :aria-expanded="open"
    @click="open = !open; editing = false; error = ''; notice = ''"
  >
    <span
      v-if="!iconOnly"
      class="server-switcher__name"
    >{{ servers.active.name }}</span>
    <AppTooltip>{{ servers.active.url }}</AppTooltip>
  </AppButton>
  <Teleport to="body">
    <template v-if="open">
      <div
        class="server-switcher__away"
        :style="{ bottom: `${windows.context.bottomInset.value}px` }"
        @click="open = false"
      />
      <aside
        class="server-switcher__panel"
        :style="{ bottom: `calc(${windows.context.bottomInset.value}px + var(--dp-space-1))` }"
        role="complementary"
        :aria-label="t('servers.switcher.servers')"
        data-testid="server-manager"
      >
        <header class="server-switcher__bar">
          <strong>{{ t('servers.switcher.servers') }}</strong>
          <AppIconButton
            :icon="appIcons.close"
            :tooltip="t('catalog.common.close')"
            @click="open = false"
          />
        </header>
        <p class="server-switcher__intro">
          {{ t('servers.switcher.intro') }}
        </p>
        <div class="server-switcher__body">
          <AppForm layout="section">
            <div class="server-switcher__current">
              {{ t('servers.switcher.current', { name: servers.active.name, url: servers.active.url }) }}
            </div>
            <template v-if="editing">
              <AppInput
                v-model="name"
                :label="t('servers.name')"
                :disable="busy"
                data-testid="server-name"
                maxlength="100"
              />
              <AppInput
                v-model="address"
                :label="t('servers.url')"
                :placeholder="t('servers.url_example')"
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
                  <span v-if="profile.url === servers.active.url">{{ t('servers.switcher.current_mark') }}</span>
                  <div class="server-switcher__url">
                    {{ profile.url }}
                  </div>
                </div>
                <AppButton
                  :label="profile.url === servers.active.url ? t('servers.switcher.check') : t('servers.switcher.connect')"
                  variant="quiet"
                  size="sm"
                  :disable="busy"
                  @click="connect(profile)"
                />
                <template v-if="profile.url !== servers.defaultServer.url">
                  <AppIconButton
                    :icon="appIcons.edit"
                    :tooltip="t('servers.switcher.edit')"
                    :aria-label="t('servers.switcher.edit')"
                    :disable="busy"
                    @click="edit(profile)"
                  />
                  <AppIconButton
                    :icon="appIcons.delete"
                    :tooltip="t('servers.switcher.remove')"
                    :aria-label="t('servers.switcher.remove')"
                    variant="danger-quiet"
                    :disable="busy"
                    @click="remove(profile)"
                  />
                </template>
              </div>
              <div>
                <AppButton
                  :label="t('servers.switcher.add')"
                  :icon="appIcons.add"
                  variant="secondary"
                  :disable="busy"
                  data-testid="server-add"
                  @click="edit()"
                />
              </div>
            </template>
          </AppForm>
        </div>
        <footer
          v-if="editing || error || notice"
          class="server-switcher__footer"
        >
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
              :label="t('servers.switcher.check_connection')"
              variant="secondary"
              :disable="busy"
              @click="checkForm"
            />
            <AppButton
              :label="t('catalog.common.cancel')"
              variant="quiet"
              :disable="busy"
              @click="editing = false; error = ''; notice = ''"
            />
            <AppButton
              :label="savingActiveAddress ? t('servers.switcher.save_and_connect') : t('servers.switcher.save')"
              :loading="busy"
              data-testid="server-save"
              @click="save"
            />
          </template>
        </footer>
      </aside>
    </template>
  </Teleport>
</template>

<style scoped>
.server-switcher { flex: none; max-width: min(var(--dp-width-note), 38vw); }
.server-switcher__name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: var(--dp-width-name); }
.server-switcher__row { display: flex; align-items: center; gap: var(--dp-space-1); padding: var(--dp-space-2) 0; border-bottom: 1px solid var(--dp-border); }
.server-switcher__details { flex: 1; min-width: 0; }
.server-switcher__url, .server-switcher__current { color: var(--dp-text-muted); font-size: var(--dp-font-size-sm); overflow-wrap: anywhere; }
.server-switcher__strip { flex-basis: 100%; display: flex; flex-direction: column; gap: var(--dp-space-2); }
.server-switcher__away, .server-switcher__panel { position: fixed; top: var(--dp-header-height); z-index: var(--dp-layer-sheet); }
.server-switcher__away { left: 0; right: 0; }
.server-switcher__panel {
  top: calc(var(--dp-header-height) + var(--dp-space-1));
  inset-inline-start: var(--dp-space-1);
  width: 420px;
  max-width: calc(100vw - var(--dp-space-2));
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  overflow: hidden;
  background: var(--dp-surface);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-panel);
  box-shadow: 8px 0 24px var(--dp-shadow-soft);
}
.server-switcher__bar { display: flex; align-items: center; gap: var(--dp-space-2); padding: var(--dp-space-2) var(--dp-space-2) var(--dp-space-2) var(--dp-space-3); border-bottom: 1px solid var(--dp-border); background: var(--dp-card-head); }
.server-switcher__bar > strong { flex: 1; }
/* The body's inset (16px) on both sides, so the intro, the fields and the commands under them share one left and one right edge. */
.server-switcher__intro { margin: 0; padding: var(--dp-space-3) var(--dp-space-4) 0; color: var(--dp-text-muted); }
.server-switcher__body { flex: 1; min-height: 0; overflow: auto; }
.server-switcher__footer { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: var(--dp-space-2); padding: var(--dp-space-2) var(--dp-space-4); border-top: 1px solid var(--dp-border); }
</style>
