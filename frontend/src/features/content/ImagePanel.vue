<script setup lang="ts">
import { computed, ref } from "vue"

import type { ContentRequest } from "@/client"
import { client } from "@/client/client.gen"
import { useContent } from "@/features/content/api"
import { useReloadable } from "@/features/workspace/reloadable"
import { messageOf } from "@/shared/api/errors"
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
    `${value.size_bytes.toLocaleString()} bytes`
  )
})

async function reload() {
  previewFailed.value = false
  await content.refetch()
}

useReloadable(props.panelId, reload)

</script>

<template>
  <div class="image-panel">
    <div class="image-panel__head">
      <span data-testid="image-details">{{ details }}</span>
    </div>

    <AppBanner
      v-if="error"
      tone="error"
      data-testid="content-error"
    >
      {{ error }}
    </AppBanner>
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
  padding: 4px;
}
.image-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 0 8px;
  border-bottom: 1px solid var(--dp-border-faint);
  color: var(--dp-text-muted);
  font-size: 11px;
}
.image-panel__stage {
  display: grid;
  flex: 1;
  min-height: 0;
  place-items: center;
  overflow: auto;
  padding: 16px;
  background: var(--dp-hover);
}
.image-panel__image {
  display: block;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
</style>
