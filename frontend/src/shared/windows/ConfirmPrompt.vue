<script setup lang="ts">
import AppActions from "@/shared/ui/AppActions.vue"
import AppButton from "@/shared/ui/AppButton.vue"
import AppSection from "@/shared/ui/AppSection.vue"

import type { ConfirmRequest } from "./presets"

defineProps<{ request: ConfirmRequest }>()
const emit = defineEmits<{ answer: [value: boolean] }>()
</script>

<template>
  <div class="confirm-prompt">
    <AppSection
      class="confirm-prompt__message"
      data-testid="confirm-message"
    >
      {{ request.message }}
    </AppSection>
    <AppActions>
      <AppButton
        variant="quiet"
        :label="request.cancelLabel ?? 'Cancel'"
        data-testid="confirm-cancel"
        @click="emit('answer', false)"
      />
      <AppButton
        :variant="request.danger === true ? 'danger' : 'primary'"
        :label="request.confirmLabel ?? 'Confirm'"
        data-testid="confirm-accept"
        @click="emit('answer', true)"
      />
    </AppActions>
  </div>
</template>

<style scoped>
.confirm-prompt {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
/* A question may carry a list — what a drop would take with it — and a list
   read as one paragraph is not a list. */
.confirm-prompt__message {
  white-space: pre-line;
}
</style>
