<script setup lang="ts">
import AppIconButton from "./AppIconButton.vue"
import AppTooltip from "./AppTooltip.vue"

/**
 * A menu of actions, anchored to the element it is placed inside.
 *
 * Items are data rather than slotted markup: a screen then names actions and
 * says nothing about how a menu looks, and `q-list`/`q-item` stay inside the
 * kit — which is what lets the lint rule forbid them everywhere else.
 */
export interface MenuItem {
  /** What the selection is reported as, and what the test addresses. */
  name: string
  label: string
  icon?: string
  /** A destructive action: coloured, never filled. Same idea as useConfirm. */
  danger?: boolean
  disable?: boolean
  /**
   * Why the line cannot be used, on hover.
   *
   * A greyed line and a barred cursor say that something is not available and
   * nothing about what would make it available, which leaves the reader to
   * guess between "wrong place", "nothing ticked" and "this source cannot".
   * The same answer the command bar gives (D69), and for the same reason it
   * hangs off a wrapper there: a disabled item is inert, so the span inside it
   * takes the pointer back for the hover alone.
   */
  hint?: string
  /** An optional removal action beside a saved entry; also its accessible label. */
  removeLabel?: string
}

defineProps<{ items: MenuItem[] }>()

const open = defineModel<boolean>({ default: false })
const emit = defineEmits<{ select: [name: string]; remove: [name: string] }>()
</script>

<template>
  <!-- Selecting an entry closes the menu. A removal button stops its click
       so deleting a saved entry neither selects it nor closes the list. -->
  <q-menu
    v-model="open"
    auto-close
  >
    <q-list
      dense
      class="app-menu"
    >
      <q-item
        v-for="item in items"
        :key="item.name"
        clickable
        :disable="item.disable === true"
        :class="item.danger === true ? 'text-negative' : undefined"
        :data-testid="`menu-item-${item.name}`"
        @click="item.disable === true ? undefined : emit('select', item.name)"
      >
        <q-item-section
          v-if="item.icon"
          avatar
          class="app-menu__icon"
        >
          <q-icon
            :name="item.icon"
            size="18px"
          />
        </q-item-section>
        <q-item-section>
          <span class="app-menu__label">
            {{ item.label }}
            <AppTooltip v-if="item.hint">{{ item.hint }}</AppTooltip>
          </span>
        </q-item-section>
        <q-item-section
          v-if="item.removeLabel"
          side
        >
          <AppIconButton
            icon="close"
            :tooltip="item.removeLabel"
            :aria-label="item.removeLabel"
            :data-testid="`menu-remove-${item.name}`"
            :disable="item.disable === true"
            compact
            @click.stop="emit('remove', item.name)"
            @keydown.enter.stop
            @keyup.enter.stop
            @keydown.space.stop
            @keyup.space.stop
          />
        </q-item-section>
      </q-item>
    </q-list>
  </q-menu>
</template>

<style scoped>
.app-menu {
  min-width: 160px;
}
.app-menu__icon {
  min-width: 28px;
  padding-right: 0;
}

/* A disabled item is inert, so a tooltip hung on it never opens. The label
   inside takes the pointer back, which is enough for a hover and not enough
   for a click — the item's own handler refuses a disabled line anyway. */
.app-menu__label { pointer-events: auto; }
</style>
