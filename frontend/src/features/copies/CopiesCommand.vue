<script setup lang="ts">
import { useCopiesWindow } from "@/features/copies/copies"
import { t } from "@/shared/i18n"
import { AppButton, AppTooltip, appIcons } from "@/shared/ui"

/** The rail button that opens and closes the copy history (D460). */
withDefaults(defineProps<{ iconOnly?: boolean }>(), { iconOnly: false })

const window = useCopiesWindow()
</script>

<template>
  <!-- The tooltip hangs off this rather than off the button, as the other
       commands on the rails do. -->
  <span class="copies-command">
    <AppButton
      :variant="window.open.value ? 'chosen' : 'quiet'"
      size="sm"
      :icon="appIcons.contentPaste"
      :label="t('copies.command.label')"
      :icon-only="iconOnly"
      :aria-pressed="window.open.value"
      data-testid="command-copies"
      @click="window.toggle()"
    />
    <AppTooltip>{{ t('copies.command.tooltip') }}</AppTooltip>
  </span>
</template>

<style scoped>
.copies-command {
  display: flex;
  align-items: center;
}
</style>
