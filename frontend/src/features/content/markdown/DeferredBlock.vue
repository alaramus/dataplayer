<script setup lang="ts">
/**
 * Mount a heavy block only when it is about to be seen, so a document of forty
 * diagrams costs one diagram to open. See D50.
 */
import { onBeforeUnmount, onMounted, ref } from "vue"

const host = ref<HTMLElement | null>(null)
const shown = ref(false)
let observer: IntersectionObserver | null = null

function stop() {
  observer?.disconnect()
  observer = null
}

function show() {
  shown.value = true
  stop()
}

onMounted(() => {
  // jsdom and any browser without the observer get the block immediately: the
  // fallback is showing more, never showing nothing.
  if (!host.value || typeof IntersectionObserver === "undefined") {
    show()
    return
  }
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) show()
    },
    { rootMargin: "240px 0px" }
  )
  observer.observe(host.value)
})

onBeforeUnmount(stop)
</script>

<template>
  <div
    ref="host"
    class="deferred-block"
  >
    <slot v-if="shown" />
    <div
      v-else
      class="deferred-block__placeholder"
      aria-hidden="true"
    />
  </div>
</template>

<style scoped>
.deferred-block {
  min-width: 0;
}
.deferred-block__placeholder {
  min-height: 180px;
  border: 1px solid var(--dp-border-faint);
  border-radius: 4px;
  background: var(--dp-hover);
}
</style>
