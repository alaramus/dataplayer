<script setup lang="ts">
import { computed, ref } from "vue"

import type { ContentRequest } from "@/client"
import { client } from "@/client/client.gen"
import { formatSize } from "@/features/catalog/nodes"
import { useContent } from "@/features/content/api"
import SourceErrorBanner from "@/features/sshKeys/SourceErrorBanner.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { errorKindOf, messageOf } from "@/shared/api/errors"
import { AppBanner, AppSpinner } from "@/shared/ui"

const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
}>()

const connectorId = computed(() => props.connectorId)
const request = computed<ContentRequest>(() => ({
  node_id: props.nodeId,
  representation: "image",
}))
const content = useContent(connectorId, request)
const errorKind = computed(() => errorKindOf(content.error.value))
const previewFailed = ref(false)

const image = computed(() => {
  const value = content.data.value
  return value?.kind === "image" ? value : null
})
const previewUrl = computed(() => {
  const url = image.value?.preview_url
  return url ? client.buildUrl({ url }) : ""
})
const error = computed(() =>
  content.isError.value ? messageOf(content.error.value, "Could not open this image") : ""
)
const details = computed(() => {
  const value = image.value
  if (value === null) return ""
  const format = value.media_type === "image/png" ? "PNG" : "JPEG"
  return (
    `${format} · ${String(value.width)} × ${String(value.height)} · ` +
    formatSize(value.size_bytes)
  )
})

async function reload() {
  previewFailed.value = false
  await content.refetch()
}

useReloadable(() => props.panelId, reload)

</script>

<template>
  <div class="image-panel">
    <div class="image-panel__head">
      <span
        class="image-panel__details"
        data-testid="image-details"
      >{{ details }}</span>
      <div class="image-panel__commands">
        <PanelCommands
          :panel-id="panelId"
          :reveal="{ connectorId, nodeId, label: title }"
        />
      </div>
    </div>

    <SourceErrorBanner
      v-if="error"
      :connector-id="connectorId"
      :error-kind="errorKind"
      data-testid="content-error"
    >
      {{ error }}
    </SourceErrorBanner>
    <AppSpinner v-else-if="content.isPending.value" />
    <AppBanner
      v-else-if="previewFailed || !previewUrl"
      tone="error"
      data-testid="image-error"
    >
      The verified preview could not be loaded. Reload this tab to request a new one.
    </AppBanner>
    <div
      v-else
      class="image-panel__stage"
    >
      <img
        :src="previewUrl"
        :alt="title"
        class="image-panel__image"
        data-testid="image-preview"
        @error="previewFailed = true"
      >
    </div>
  </div>
</template>

<style scoped>
.image-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: var(--dp-space-1);
}
.image-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 0 var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border-faint);
}

/* On the words and not on the head that holds them: a flat button takes its
   colour from whatever contains it, so a muted head drew the commands beside
   this line in the colour of a disabled control. */
.image-panel__details {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
}
.image-panel__commands {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
}
.image-panel__stage {
  display: grid;
  flex: 1;
  min-height: 0;
  place-items: center;
  overflow: auto;
  padding: var(--dp-space-4);
  background: var(--dp-hover);
}
.image-panel__image {
  display: block;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
</style>
