<script setup lang="ts">
import { computed } from "vue"

import { useConnectors } from "@/features/connectors/api"
import { sceneStage } from "@/features/workspace/scene"
import { useWorkspaceActions } from "@/features/workspace/state"
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
 * The keys that do the same thing, if there are any.
 *
 * The application has no global shortcut yet, so this is empty and nothing is
 * drawn: an empty frame promising keys that do not exist is worse than no
 * frame. Keys are their own sub-project; the layout is ready for them.
 */
const shortcuts: { keys: string; action: string }[] = []
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
          DataPlayer
        </h1>
        <p class="scene__text">
          Connect to a database or to your own files, walk through what is in it, and read it
          here.
        </p>
        <div class="scene__actions">
          <!-- A real button, and not "press the plus on the left": sending
               somebody to look for a control elsewhere on the screen when it
               can be given here is worse than giving it. -->
          <AppButton
            label="Add connection"
            icon="add"
            data-testid="scene-add-connector"
            @click="workspace.editConnector(null)"
          />
        </div>
      </template>

      <template v-else-if="stage === 'pick-connection'">
        <p class="scene__text">
          Pick a connection on the left to browse what is in it.
        </p>
      </template>

      <template v-else>
        <p class="scene__text">
          Pick a table or a file in the catalog to read it here.
        </p>
        <!-- About this level rather than about the application: what is worth
             saying is the thing the screen does not show until you find it. -->
        <p class="scene__hint">
          Tick nodes in the catalog and the menu in its head says what can be done with them.
        </p>
      </template>

      <dl
        v-if="shortcuts.length > 0"
        class="scene__keys"
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
  padding: 24px;
}
.scene__body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  max-width: 380px;
  text-align: center;
}
.scene__title {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
  color: var(--dp-text-strong);
}
.scene__text {
  margin: 0;
  color: var(--dp-text-muted);
}
.scene__hint {
  margin: 0;
  font-size: 12px;
  color: var(--dp-text-faint);
}
.scene__actions {
  margin-top: 8px;
}
.scene__keys {
  display: grid;
  grid-template-columns: auto auto;
  gap: 2px 8px;
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--dp-text-faint);
}
</style>
