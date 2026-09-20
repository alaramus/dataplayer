<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute } from "vue-router"

import { useActiveServerCheck } from "./api"
import ServerSwitcher from "./ServerSwitcher.vue"
import AppBanner from "@/shared/ui/AppBanner.vue"
import AppButton from "@/shared/ui/AppButton.vue"
import AppCard from "@/shared/ui/AppCard.vue"
import AppSection from "@/shared/ui/AppSection.vue"
import AppSpinner from "@/shared/ui/AppSpinner.vue"
import { useServersStore } from "@/stores/servers"

const route = useRoute()
const servers = useServersStore()
const required = computed(() => route.name != null && !["connect-server", "ui-kit", "workspace-demo"].includes(String(route.name)))
const status = useActiveServerCheck(required)
// A later failed health check must not unmount an editor with unsaved work.
const admitted = ref(false)
watch(status.data, (value) => { if (value === true) admitted.value = true }, { immediate: true })
</script>

<template>
  <slot v-if="!required || route.name === 'login' || admitted" />
  <!-- Still asking. Nothing is claimed about the server yet, so nothing is
       said: a reload used to draw the whole "cannot connect" card for the
       fraction of a second the first health check takes. -->
  <div
    v-else-if="status.isPending.value"
    class="server-boundary server-boundary--waiting"
    data-testid="server-connecting"
  >
    <AppSpinner />
  </div>
  <div
    v-else
    class="server-boundary"
  >
    <AppCard
      size="sm"
      title="Connect to DataPlayer"
    >
      <AppSection gutter>
        <ServerSwitcher />
        <div class="server-boundary__url">
          {{ servers.active.url }}
        </div>
        <AppBanner
          v-if="status.isError.value"
          tone="error"
        >
          {{ status.error.value?.message }}
        </AppBanner>
        <AppButton
          label="Retry connection"
          :loading="status.isFetching.value"
          @click="status.refetch()"
        />
      </AppSection>
    </AppCard>
  </div>
</template>

<style scoped>
.server-boundary { min-height: 100vh; display: grid; place-items: center; padding: var(--dp-space-4); }
.server-boundary__url { overflow-wrap: anywhere; }

/* Even a spinner is a flash when the answer takes 80ms. It appears only if
   the wait is long enough to be worth explaining — a delay rather than a
   timer, so nothing has to be cleaned up. */
.server-boundary--waiting {
  opacity: 0;
  animation: server-boundary-appear 0s linear 400ms forwards;
}
@keyframes server-boundary-appear {
  to { opacity: 1; }
}
</style>
