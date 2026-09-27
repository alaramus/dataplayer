<script setup lang="ts">
/**
 * A scrolled column whose scrollbar takes no room.
 *
 * The bar is drawn over the edge of what it scrolls, and only while the
 * pointer is over it or it is moving. A native one takes its width from the
 * content: in a rail forty pixels wide that was a third of it, and the icons
 * stood off the centre of the plus above them.
 */
</script>

<template>
  <q-scroll-area class="app-scroll-area">
    <slot />
  </q-scroll-area>
</template>

<style scoped>
/* Stretched rather than sized by what it holds: the area contains its size
   strictly, and a column that centres its children gave it a width of none. */
.app-scroll-area {
  flex: 1;
  align-self: stretch;
  min-height: 0;
}
/* Quasar hides the bar with an !important opacity of none, so these apply only
   while it is shown. */
.app-scroll-area :deep(.q-scrollarea__thumb) {
  width: 4px;
  right: 1px;
  border-radius: var(--dp-radius-control);
  background: var(--dp-text-muted);
  opacity: 0.5;
}
.app-scroll-area :deep(.q-scrollarea__thumb:hover) {
  opacity: 0.8;
}
</style>
