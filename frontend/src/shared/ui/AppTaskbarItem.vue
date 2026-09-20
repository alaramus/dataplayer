<script setup lang="ts">
import AppButton from "./AppButton.vue"
import AppIconButton from "./AppIconButton.vue"
import AppTooltip from "./AppTooltip.vue"
import { panelColorStyle } from "./panelColor"

/**
 * One thing on the bar at the foot of the screen.
 *
 * A window, or a section of the workspace put aside: both are something that
 * is open and not in front of you, and a desktop draws them the same way. The
 * shape lives here once, so the two bars cannot drift into two shapes for one
 * meaning.
 */
withDefaults(
  defineProps<{
    title: string
    icon?: string
    /** #RRGGBB of whatever this belongs to, for the tab's own colouring. */
    color?: string | null
    /** The one being looked at now. */
    front?: boolean
    /** Open, and not on the screen. */
    aside?: boolean
    /** Hover text, where the title alone does not say what pressing does. */
    tooltip?: string
    /** The label of the cross, where there is one. Without it there is none. */
    closeLabel?: string
    /**
     * What a test addresses the cross by.
     *
     * Two buttons in one component, so one `data-testid` cannot name both: the
     * attribute goes to the one that opens, which is the item itself, and the
     * cross is named here.
     */
    closeTestId?: string
  }>(),
  {
    icon: "web_asset",
    color: null,
    front: false,
    aside: false,
    tooltip: undefined,
    closeLabel: undefined,
    closeTestId: undefined,
  }
)

const emit = defineEmits<{ open: []; close: [] }>()

// Whatever the caller put on this component belongs to the button that opens:
// that is the thing being pressed, and the thing a bar puts focus on after
// something is put aside.
defineOptions({ inheritAttrs: false })
</script>

<template>
  <div
    class="taskbar-item"
    :class="{ 'taskbar-item--front': front, 'taskbar-item--aside': aside }"
    :style="panelColorStyle(color)"
  >
    <AppButton
      v-bind="$attrs"
      class="taskbar-item__open"
      variant="quiet"
      size="sm"
      :icon="icon"
      :aria-label="title"
      :aria-pressed="front"
      @click="emit('open')"
    >
      <span class="taskbar-item__title">{{ title }}</span>
      <AppTooltip>{{ tooltip ?? title }}</AppTooltip>
    </AppButton>
    <AppIconButton
      v-if="closeLabel"
      class="taskbar-item__close"
      icon="close"
      compact
      :tooltip="closeLabel"
      :aria-label="closeLabel"
      :data-testid="closeTestId"
      @click="emit('close')"
    />
  </div>
</template>

<style scoped>
.taskbar-item {
  /* Gives room up before the row runs out of it: nine windows shrink to their
     icons and a word rather than pushing the ninth off the end, where the only
     way to it is a wheel nobody knows to use. */
  flex: 0 1 auto;
  display: flex;
  align-items: center;
  min-width: 44px;
  max-width: 150px;
  max-height: 100%;
  overflow: hidden;
  /* Outline rather than border: a border takes room in the layout, so the
     first tab added two pixels to the footer the moment it appeared. */
  outline: 1px solid transparent;
  outline-offset: -1px;
  border-radius: var(--dp-radius-control);
  background: var(--dp-panel-background, var(--dp-hover));
  color: var(--dp-panel-foreground, inherit);
}
/* The one actually being looked at, marked the way a desktop marks it. */
.taskbar-item--front {
  outline-color: var(--dp-focus-border);
  background: var(--dp-panel-background, var(--dp-active));
}
/* Put aside: still on the bar, and visibly not on screen. */
.taskbar-item--aside {
  opacity: 0.65;
}
.taskbar-item__open {
  flex: 1 1 auto;
  min-width: 0;
  max-width: 100%;
}
.taskbar-item__open :deep(.q-btn__content) {
  flex-wrap: nowrap;
  min-width: 0;
  overflow: hidden;
  gap: var(--dp-space-1);
}
.taskbar-item__close {
  flex: none;
}
.taskbar-item__title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
