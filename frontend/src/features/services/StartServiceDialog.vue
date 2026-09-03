<script setup lang="ts">
import { ref, watch } from "vue"

import type { ServiceTemplateInfo } from "@/client"
import { AppButton, AppInput } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * The one question worth asking before a database is started here.
 *
 * Not the image, not the port, not the password — those are the server's
 * (D80). What it is called is the one thing only the person asking knows, and
 * a connection called "PostgreSQL" is no use to somebody who starts two.
 */
const props = defineProps<{
  template: ServiceTemplateInfo | null
}>()

const emit = defineEmits<{
  "update:template": [value: ServiceTemplateInfo | null]
  start: [payload: { templateKey: string; name: string }]
}>()

const name = ref("")

// Opened on a template, it starts on that template's own words for itself.
watch(
  () => props.template,
  (template) => {
    name.value = template?.title ?? ""
  }
)

function start() {
  const template = props.template
  if (!template || name.value.trim() === "") return
  emit("start", { templateKey: template.key, name: name.value.trim() })
  emit("update:template", null)
}
</script>

<template>
  <WindowDialog
    :model-value="template !== null"
    size="sm"
    :title="`Start ${template?.title ?? ''} here`"
    subtitle="This server runs it and saves the connection for you."
    data-testid="start-service-dialog"
    @update:model-value="emit('update:template', null)"
  >
    <div class="start-service">
      <AppInput
        v-model="name"
        label="Name this connection"
        data-testid="service-name"
        @keydown.enter="start"
      />
      <p class="start-service__what">
        Runs <code>{{ template?.image }}</code> on this server, with a password
        nobody has to choose.
      </p>
    </div>

    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="emit('update:template', null)"
      />
      <AppButton
        label="Start"
        :disable="name.trim() === ''"
        data-testid="start-service-confirm"
        @click="start"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.start-service {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 2px;
}
.start-service__what {
  margin: 0;
  font-size: 12px;
  color: var(--dp-text-muted);
}
</style>
