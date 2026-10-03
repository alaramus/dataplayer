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
/* A column scrolls one way. Quasar positions the content absolutely with only
   a minimum width, so a nowrap line widened it past the area, nothing inside
   could cut itself with an ellipsis, and a horizontal bar appeared. */
.app-scroll-area :deep(.q-scrollarea__content) {
  width: 100%;
}
.app-scroll-area :deep(.q-scrollarea__bar--h),
.app-scroll-area :deep(.q-scrollarea__thumb--h) {
  display: none;
}
/* Quasar hides the bar with an !important opacity of none, so these apply only
   while it is shown. Native overflow areas use the same theme thumb. */
.app-scroll-area :deep(.q-scrollarea__thumb--v) {
  width: var(--dp-scrollbar-size);
  right: 1px;
  border-radius: var(--dp-radius-control);
  background: var(--dp-scrollbar-thumb);
  opacity: 1;
}
.app-scroll-area :deep(.q-scrollarea__thumb--v:hover) {
  background: var(--dp-scrollbar-thumb-hover);
}
/* Quasar gives the bar and its thumb a grab hand; a native scrollbar, which
   is every other one in the application, keeps the arrow. */
.app-scroll-area :deep(.q-scrollarea__bar),
.app-scroll-area :deep(.q-scrollarea__thumb) {
  cursor: default;
}
</style>
