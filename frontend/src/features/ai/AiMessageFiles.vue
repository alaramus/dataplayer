<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue"

import type { MessageAttachmentPublic } from "@/client"
import { useToast } from "@/shared/ui"
import { messageOf } from "@/shared/api/errors"

import AiFileChip from "./AiFileChip.vue"
import { fetchAiAttachment } from "./api"

/**
 * The files a sent message carried (D142).
 *
 * Fetched with the person's token rather than linked: an image address in an
 * `<img>` carries no Authorization header, so each file is read as a blob and
 * drawn from an address of this page, released when the message goes.
 */
const props = defineProps<{ conversationId: string; files: MessageAttachmentPublic[] }>()
const toast = useToast()
const addresses = ref(new Map<string, string>())

async function addressOf(file: MessageAttachmentPublic): Promise<string> {
  const known = addresses.value.get(file.id)
  if (known !== undefined) return known
  const address = URL.createObjectURL(await fetchAiAttachment(props.conversationId, file.id))
  addresses.value = new Map(addresses.value).set(file.id, address)
  return address
}

// Images are drawn at once; text is fetched only when somebody opens it.
watch(
  () => props.files,
  (files) => {
    for (const file of files) {
      if (file.kind === "image") addressOf(file).catch(() => undefined)
    }
  },
  { immediate: true }
)

async function open(file: MessageAttachmentPublic) {
  try {
    window.open(await addressOf(file), "_blank", "noopener")
  } catch (cause) {
    toast.error(messageOf(cause, `${file.name} could not be opened`))
  }
}

onBeforeUnmount(() => {
  for (const address of addresses.value.values()) URL.revokeObjectURL(address)
})
</script>

<template>
  <div
    class="ai-message-files"
    data-testid="ai-message-files"
  >
    <AiFileChip
      v-for="file in files"
      :key="file.id"
      :name="file.name"
      :size="file.size"
      :kind="file.kind"
      :thumbnail="addresses.get(file.id) ?? null"
      @open="open(file)"
    />
  </div>
</template>

<style scoped>
.ai-message-files {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--dp-space-1);
  max-width: 78%;
  margin-bottom: var(--dp-space-1);
}
</style>
