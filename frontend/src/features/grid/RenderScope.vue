<!--
  Draws its slot and nothing else, as a component of its own.

  The trap it exists for: what a slot reads is tracked by the component that
  renders the slot, not by the one that wrote it. Wrapped in this, the rows a
  grid draws follow the scroll position without the grid itself re-rendering —
  which would redraw the command row above it, every button and tooltip, on
  every row scrolled past.
-->
<template>
  <slot />
</template>
