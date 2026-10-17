<script setup lang="ts">
import { computed } from "vue"

import { useBottomPanel } from "@/features/workspace/useBottomPanel"
import { t } from "@/shared/i18n"
import { AppButton, AppTooltip, appIcons } from "@/shared/ui"

/**
 * The switch of the Search index tool in the panel at the foot of the
 * workspace (D212, D143), beside Services, Terminals and Queries.
 */
withDefaults(defineProps<{ iconOnly?: boolean }>(), { iconOnly: false })

const panel = useBottomPanel()
const shown = computed(() => panel.open.value === "search-index")
</script>

<template>
  <!-- The tooltip hangs off this rather than off the button, as the other
       commands on the rails do. -->
  <span class="search-index-command">
    <AppButton
      :variant="shown ? 'chosen' : 'quiet'"
      size="sm"
      :icon="appIcons.manageSearch"
      :label="t('search_index.command.label')"
      :icon-only="iconOnly"
      :aria-pressed="shown"
      data-testid="command-search-index"
      @click="panel.toggle('search-index')"
    />
    <AppTooltip>{{ t('search_index.command.tooltip') }}</AppTooltip>
  </span>
</template>

<style scoped>
.search-index-command {
  display: flex;
  align-items: center;
}
</style>
