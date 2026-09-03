<script setup lang="ts">
import ManagedServices from "@/features/services/ManagedServices.vue"
import { WindowDialog } from "@/shared/windows"

/**
 * The window the bar's Services button opens.
 *
 * A window rather than a strip above the connections, because that column is
 * a fifth of the screen and holds every connection a person has: a service is
 * looked at while something is being done to it and not otherwise. The list
 * is the same component, with room now to say what each one is (D69).
 */
defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    size="lg"
    title="Services on this server"
    subtitle="Started here, and removed here with everything they hold."
    data-testid="services-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <ManagedServices />
  </WindowDialog>
</template>
