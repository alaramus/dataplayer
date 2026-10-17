<script setup lang="ts">
import { ref } from "vue"

import { t } from "@/shared/i18n"

import AppActions from "@/shared/ui/AppActions.vue"
import AppButton from "@/shared/ui/AppButton.vue"
import AppCheckbox from "@/shared/ui/AppCheckbox.vue"
import AppRadioGroup from "@/shared/ui/AppRadioGroup.vue"
import AppSection from "@/shared/ui/AppSection.vue"

import type { ConfirmRequest } from "./presets"

const props = defineProps<{ request: ConfirmRequest }>()
const emit = defineEmits<{ answer: [value: boolean] }>()

/** Ticked here and read on the way out; nothing else watches it. */
const remember = ref(false)
/** The second thing this press decides, when the question carries one. */
const also = ref(props.request.alsoDefault ?? false)
const choice = ref(props.request.choiceDefault ?? props.request.choices?.[0]?.value ?? "")

function accept() {
  if (remember.value) props.request.onRemember?.()
  // Both answers, not only the ticked one: this box is part of what is being
  // agreed to rather than a request to stop asking.
  props.request.onAlso?.(also.value)
  if (props.request.choices?.length) props.request.onChoice?.(choice.value)
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
    <AppRadioGroup
      v-if="request.choices?.length"
      v-model="choice"
      :options="request.choices"
      :aria-label="request.title"
      class="confirm-prompt__choices"
      data-testid="confirm-choice"
    />
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
        :label="request.cancelLabel ?? t('catalog.common.cancel')"
        data-testid="confirm-cancel"
        @click="emit('answer', false)"
      />
      <AppButton
        :variant="request.danger === true ? 'danger' : 'primary'"
        :label="request.confirmLabel ?? t('windows.confirm')"
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
/* The answers stand under the question they answer, inset as its text is. */
.confirm-prompt__choices {
  flex: none;
  padding: 0 var(--dp-space-3) var(--dp-space-2);
}
/* Under the question and above the buttons, where it reads as part of the
   answer rather than as another thing being asked. */
.confirm-prompt__remember {
  flex: none;
  padding: 0 var(--dp-space-3);
  font-size: var(--dp-font-size-sm);
}
</style>
