<script setup lang="ts">
import AppIconButton from "./AppIconButton.vue"
import AppTooltip from "./AppTooltip.vue"
import { appIcons } from "./icons"

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
      role="menu"
    >
      <!-- A line that cannot be used is still a line of this menu. Disabled,
           Quasar draws it as neither an item nor a control, so a reader met
           four words of loose text where a command had been; it now says what
           it is, that it is off, and why - the reason in the name rather than
           in a tooltip nothing but a pointer can open (U14). Quasar keeps the
           tab stop to itself and gives a disabled item none, so walking the
           menu is how the line is met. -->
      <q-item
        v-for="item in items"
        :key="item.name"
        clickable
        role="menuitem"
        :disable="item.disable === true"
        :aria-disabled="item.disable === true ? 'true' : undefined"
        :aria-label="item.disable === true && item.hint ? `${item.label} — ${item.hint}` : undefined"
        :class="item.danger === true ? 'text-dp-action-danger' : undefined"
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
            size="var(--dp-icon-sm)"
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
            :icon="appIcons.close"
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
