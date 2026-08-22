<script setup lang="ts">
import { computed, useSlots } from "vue"

import AppActions from "./AppActions.vue"
import AppSection from "./AppSection.vue"
import { panelStyle } from "./tokens"
import type { PanelSize } from "./tokens"

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    title?: string
    subtitle?: string
    size?: PanelSize
    persistent?: boolean
  }>(),
  { title: undefined, subtitle: undefined, size: "md", persistent: false }
)

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()

defineOptions({ inheritAttrs: false })

const slots = useSlots()
const style = computed(() => panelStyle(props.size))
</script>

<template>
  <!--
    Attributes are steered onto the card rather than left on QDialog: QDialog
    renders through a teleport, so an attribute left on it reaches no element a
    reader or a test can address. The card is what is on screen, so it carries
    data-testid.
  -->
  <q-dialog
    :model-value="modelValue"
    :persistent="persistent"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <q-card
      v-bind="$attrs"
      :style="{ width: style.width, maxWidth: style.maxWidth }"
    >
      <AppSection v-if="title ?? subtitle">
        <div
          v-if="title"
          class="text-h6"
        >
          {{ title }}
        </div>
        <div
          v-if="subtitle"
          class="text-caption text-grey"
        >
          {{ subtitle }}
        </div>
      </AppSection>

      <slot />

      <AppActions v-if="slots.actions">
        <slot name="actions" />
      </AppActions>
    </q-card>
  </q-dialog>
</template>
