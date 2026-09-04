<script setup lang="ts">
import { ref } from "vue"

import AppActions from "@/shared/ui/AppActions.vue"
import AppButton from "@/shared/ui/AppButton.vue"
import AppCheckbox from "@/shared/ui/AppCheckbox.vue"
import AppSection from "@/shared/ui/AppSection.vue"

import type { ConfirmRequest } from "./presets"

const props = defineProps<{ request: ConfirmRequest }>()
const emit = defineEmits<{ answer: [value: boolean] }>()

/** Ticked here and read on the way out; nothing else watches it. */
const remember = ref(false)
/** The second thing this press decides, when the question carries one. */
const also = ref(props.request.alsoDefault ?? false)

function accept() {
  if (remember.value) props.request.onRemember?.()
  // Both answers, not only the ticked one: this box is part of what is being
  // agreed to rather than a request to stop asking.
  props.request.onAlso?.(also.value)
  emit("answer", true)
}
</script>

<template>
  <div class="confirm-prompt">
    <AppSection
      class="confirm-prompt__message"
      data-testid="confirm-message"
    >
      {{ request.message }}
    </AppSection>
    <AppCheckbox
      v-if="request.alsoLabel"
      v-model="also"
      :label="request.alsoLabel"
      dense
      class="confirm-prompt__remember"
      data-testid="confirm-also"
    />
    <AppCheckbox
      v-if="request.rememberLabel"
      v-model="remember"
      :label="request.rememberLabel"
      dense
      class="confirm-prompt__remember"
      data-testid="confirm-remember"
    />
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
        @click="accept"
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
/* Under the question and above the buttons, where it reads as part of the
   answer rather than as another thing being asked. */
.confirm-prompt__remember {
  flex: none;
  padding: 0 12px;
  font-size: 12px;
}
</style>
