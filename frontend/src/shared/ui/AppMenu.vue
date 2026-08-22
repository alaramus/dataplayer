<script setup lang="ts">
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
}

defineProps<{ items: MenuItem[] }>()

const emit = defineEmits<{ select: [name: string] }>()
</script>

<template>
  <!-- auto-close: every item here is a command, so none of them leaves the
       menu open. A menu of toggles would need its own component. -->
  <q-menu auto-close>
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
        <q-item-section>{{ item.label }}</q-item-section>
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
</style>
