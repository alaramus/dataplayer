<script setup lang="ts">
import AppIconButton from "./AppIconButton.vue"

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
   * Why the line cannot be used, under the label.
   *
   * A greyed line and a barred cursor say that something is not available and
   * nothing about what would make it available, which leaves the reader to
   * guess between "wrong place", "nothing ticked" and "this source cannot".
   * The same reasoning as the command bar's tooltips (D69), said in the menu
   * itself because a disabled item takes no pointer events and so has no
   * hover of its own.
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
        @click="emit('select', item.name)"
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
          <q-item-label>{{ item.label }}</q-item-label>
          <q-item-label
            v-if="item.hint"
            caption
            class="app-menu__hint"
          >
            {{ item.hint }}
          </q-item-label>
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

/* Quasar dims a disabled item as a whole, and a caption dimmed twice over is
   the one line in it that has to stay readable. */
.app-menu__hint {
  color: var(--dp-text-muted);
  white-space: normal;
  max-width: 260px;
}
</style>
