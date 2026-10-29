<script setup lang="ts">
import type { QMenuProps } from "quasar"

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
  /** Lines of a submenu opened from this one, which then selects nothing itself. */
  children?: MenuItem[]
}

withDefaults(
  defineProps<{
    items: MenuItem[]
    /** Where the menu opens against what holds it; Quasar's own placement when unset. */
    anchor?: QMenuProps["anchor"]
    self?: QMenuProps["self"]
  }>(),
  { anchor: undefined, self: undefined }
)

const open = defineModel<boolean>({ default: false })
const emit = defineEmits<{ select: [name: string]; remove: [name: string] }>()
</script>

<template>
  <!-- Selecting an entry closes the menu and every menu it was opened from;
       not auto-close, which closes on the line that opens a submenu too. A
       removal button stops its click so deleting a saved entry neither selects
       it nor closes the list. -->
  <q-menu
    v-model="open"
    :anchor="anchor"
    :self="self"
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
      <template
        v-for="item in items"
        :key="item.name"
      >
        <q-item
          v-if="item.children"
          clickable
          role="menuitem"
          aria-haspopup="menu"
          :disable="item.disable === true"
          :aria-disabled="item.disable === true ? 'true' : undefined"
          :data-testid="`menu-item-${item.name}`"
        >
          <q-item-section>
            <span class="app-menu__label">{{ item.label }}</span>
          </q-item-section>
          <q-item-section side>
            <q-icon
              :name="appIcons.chevronRight"
              size="var(--dp-icon-sm)"
            />
          </q-item-section>
          <!-- The same component one level down, so a line of a submenu is
               drawn, disabled and explained exactly as a line of this one. -->
          <AppMenu
            :items="item.children"
            anchor="top end"
            self="top start"
            @select="emit('select', $event)"
            @remove="emit('remove', $event)"
          />
        </q-item>
        <q-item
          v-else
          v-close-popup="-1"
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
              <AppTooltip
                v-if="item.hint"
                beside
              >{{ item.hint }}</AppTooltip>
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
      </template>
    </q-list>
  </q-menu>
</template>

<style scoped>
.app-menu {
  min-width: 160px;
}
.app-menu__icon {
  min-width: 28px;
  padding-inline-end: 0;
}

/* A disabled item is inert, so a tooltip hung on it never opens. The label
   inside takes the pointer back, which is enough for a hover and not enough
   for a click — the item's own handler refuses a disabled line anyway. */
.app-menu__label { pointer-events: auto; }
/* The whole width of the line, so a reason told beside it starts past the
   menu's edge rather than after the last letter of the label. */
.app-menu__label { display: block; }
</style>
