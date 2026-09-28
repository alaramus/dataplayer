<script setup lang="ts">
/**
 * The head of a card: one height, one ground and one line under it on every
 * screen, so a card of Data, of the dashboards and of the chats read as the
 * same thing. The tab strip of a Data section is drawn from the same tokens
 * in WorkspaceLeaf, which lays its tabs out itself.
 *
 * A title first, anything else after it, and the `actions` slot at the end.
 */
defineProps<{ title?: string }>()
</script>

<template>
  <div class="app-card-head">
    <span
      v-if="title"
      class="app-card-head__title"
    >{{ title }}</span>
    <slot />
    <span
      v-if="$slots.actions"
      class="app-card-head__actions"
    >
      <slot name="actions" />
    </span>
  </div>
</template>

<style scoped>
.app-card-head {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  min-width: 0;
  /* A height and not a floor: a dense button is 32px, and with the line
     under it a head that grew around one stood a pixel taller than the one
     beside it holding only a title. */
  height: var(--dp-tab-strip-height);
  padding: 0 var(--dp-space-1) 0 var(--dp-space-2);
  box-sizing: border-box;
  border-bottom: 1px solid var(--dp-border);
  background: var(--dp-card-head);
  /* The body's colour, as the head of a column in the data workspace is
     written: in --dp-text-strong, a group's heading, every space but Data
     read a shade dimmer than the one it was switched from. */
  color: inherit;
}
.app-card-head__title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
.app-card-head__actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  margin-left: auto;
}
/* Trap: a dense Quasar field's control is 40px, taller than the head, and it
   spilt over the line under it. A field here takes the room inside the head,
   which is its height less that line. */
.app-card-head :deep(.q-field__control),
.app-card-head :deep(.q-field__marginal) {
  height: calc(var(--dp-tab-strip-height) - 1px);
  min-height: calc(var(--dp-tab-strip-height) - 1px);
}
.app-card-head :deep(.q-field__native) {
  min-height: calc(var(--dp-tab-strip-height) - 1px);
  padding: 0;
}
</style>
