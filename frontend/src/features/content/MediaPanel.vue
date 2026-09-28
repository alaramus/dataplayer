<script setup lang="ts">
import { computed, ref } from "vue"

import type { ContentRequest } from "@/client"
import { client } from "@/client/client.gen"
import { useContent } from "@/features/content/api"
import { mediaDetails } from "@/features/content/media"
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
  representation: "audio" | "video"
}>()

const connectorId = computed(() => props.connectorId)
const request = computed<ContentRequest>(() => ({
  node_id: props.nodeId,
  representation: props.representation,
}))
const content = useContent(connectorId, request)
const errorKind = computed(() => errorKindOf(content.error.value))
/** What the element itself says went wrong, which is where a codec fails. */
const playbackFailed = ref(false)

const media = computed(() => {
  const value = content.data.value
  if (value?.kind === "audio" || value?.kind === "video") return value
  return null
})
const streamUrl = computed(() => {
  const url = media.value?.stream_url
  return url ? client.buildUrl({ url }) : ""
})
const details = computed(() => (media.value === null ? "" : mediaDetails(media.value)))
const error = computed(() =>
  content.isError.value
    ? messageOf(content.error.value, "Could not open this file")
    : ""
)

async function reload() {
  playbackFailed.value = false
  await content.refetch()
}

useReloadable(() => props.panelId, reload)
</script>

<template>
  <div class="media-panel">
    <div class="media-panel__head">
      <span
        class="media-panel__details"
        data-testid="media-details"
      >{{ details }}</span>
      <div class="media-panel__commands">
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
    <template v-else-if="streamUrl">
      <!-- The element's own failure is shown rather than swallowed: the
           container was verified, its codecs were not, and whether this
           browser can play them is its answer to give (D52). -->
      <AppBanner
        v-if="playbackFailed"
        tone="warning"
        data-testid="media-error"
      >
        This browser could not play the file. Its container is what the source
        verified; the codecs inside it are the player's own business.
      </AppBanner>
      <div class="media-panel__stage">
        <video
          v-if="representation === 'video'"
          :src="streamUrl"
          controls
          preload="metadata"
          class="media-panel__video"
          data-testid="media-player"
          @error="playbackFailed = true"
        />
        <audio
          v-else
          :src="streamUrl"
          controls
          preload="metadata"
          class="media-panel__audio"
          data-testid="media-player"
          @error="playbackFailed = true"
        />
      </div>
    </template>
    <AppBanner
      v-else
      tone="error"
      data-testid="media-error"
    >
      The stream could not be opened. Reload this tab to ask for a new one.
    </AppBanner>
  </div>
</template>

<style scoped>
.media-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: var(--dp-space-1);
}
.media-panel__commands {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
}
.media-panel__head {
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
.media-panel__details {
  color: var(--dp-text-muted);
  font-size: 11px;
}
.media-panel__stage {
  display: grid;
  flex: 1;
  min-height: 0;
  place-items: center;
  overflow: auto;
  padding: var(--dp-space-4);
  background: var(--dp-hover);
}
.media-panel__video {
  max-width: 100%;
  max-height: 100%;
}
.media-panel__audio {
  width: min(100%, 480px);
}
</style>
