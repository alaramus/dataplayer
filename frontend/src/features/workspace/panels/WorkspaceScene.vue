<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import { useConnectors } from "@/features/connectors/api"
import { sceneStage } from "@/features/workspace/scene"
import { useWorkspaceActions } from "@/features/workspace/state"
import { shortcutList } from "@/shared/keys/shortcuts"
import { t } from "@/shared/i18n"
import { AppButton } from "@/shared/ui"

/**
 * The empty view of the column of data, and the only column that has one.
 *
 * It carries the whole first run: a screen of three columns two of which are
 * blank looks broken rather than empty, so the other two appear with what goes
 * in them and this one says what to do next. The stage is derived, never
 * stored — see `scene.ts` and P5.
 */
const workspace = useWorkspaceActions()
const connectors = useConnectors()

const stage = computed(() =>
  sceneStage({
    loading: connectors.isLoading.value,
    connectorCount: connectors.data.value?.data.length ?? 0,
    activeConnectorId: workspace.activeConnectorId.value,
  })
)

/**
 * The keys that work here, read off the registry rather than written out: a
 * key drawn in this frame is one somebody registered, and an empty registry
 * draws no frame at all.
 */
const shortcuts = shortcutList

/** The product's name, which no language translates. */
const PRODUCT = "DataPlayer"
</script>

<template>
  <div
    class="scene"
    data-testid="workspace-scene"
    :data-stage="stage"
  >
    <div
      v-if="stage !== 'loading'"
      class="scene__body"
    >
      <template v-if="stage === 'no-connections'">
        <h1 class="scene__title">
          {{ PRODUCT }}
        </h1>
        <p class="scene__text">
          {{ t('workspace.scene.intro') }}
        </p>
        <div class="scene__actions">
          <!-- A real button, and not "press the plus on the left": sending
               somebody to look for a control elsewhere on the screen when it
               can be given here is worse than giving it. -->
          <AppButton
            :label="t('workspace.scene.add_connection')"
            :icon="appIcons.add"
            data-testid="scene-add-connector"
            @click="workspace.editConnector(null)"
          />
        </div>
      </template>

      <template v-else-if="stage === 'pick-connection'">
        <p class="scene__text">
          {{ t('workspace.scene.pick_connection') }}
        </p>
      </template>

      <template v-else>
        <p class="scene__text">
          {{ t('workspace.scene.pick_node') }}
        </p>
        <!-- About this level rather than about the application: what is worth
             saying is the thing the screen does not show until you find it. -->
        <p class="scene__hint">
          {{ t('workspace.scene.tick_hint') }}
        </p>
      </template>

      <dl
        v-if="shortcuts.length > 0"
        class="scene__keys"
        data-testid="scene-keys"
      >
        <template
          v-for="shortcut in shortcuts"
          :key="shortcut.keys"
        >
          <dt>{{ shortcut.keys }}</dt>
          <dd>{{ shortcut.action }}</dd>
        </template>
      </dl>
    </div>
  </div>
</template>

<style scoped>
.scene {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: var(--dp-space-5);
}
.scene__body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--dp-space-2);
  max-width: var(--dp-width-popover);
  text-align: center;
}
.scene__title {
  font-size: var(--dp-font-size-page);
  font-weight: 500;
  line-height: var(--dp-line-height-page);
  color: var(--dp-text);
}
.scene__text {
  margin: 0;
  color: var(--dp-text-muted);
}
.scene__hint {
  margin: 0;
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height-sm);
  color: var(--dp-text-muted);
}
.scene__actions {
  margin-top: var(--dp-space-2);
}
.scene__keys {
  display: grid;
  grid-template-columns: auto auto;
  gap: var(--dp-space-half) var(--dp-space-2);
  margin: var(--dp-space-2) 0 0;
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height-sm);
  color: var(--dp-text-muted);
}
/* The browser indents a <dd> by 40px, which stood the action that far from
   its keys. Keys to the right of their column, action to the left: a pair. */
.scene__keys dt {
  text-align: end;
}
.scene__keys dd {
  margin: 0;
  text-align: start;
}
</style>
