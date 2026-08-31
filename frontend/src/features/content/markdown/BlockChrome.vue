<script setup lang="ts">
/**
 * The frame every rich block wears: what it is on the left, what can be done
 * with it on the right.
 *
 * One component rather than four headers, because a diagram, a chart, an image
 * and a listing all offer the same kinds of thing — copy the source, save the
 * picture — and a reader should not have to learn a different corner for each.
 */
withDefaults(
  defineProps<{
    label: string
    /** A colour that carries meaning, for blocks whose kind is the point. */
    accent?: string | null
    icon?: string | null
  }>(),
  { accent: null, icon: null }
)
</script>

<template>
  <figure
    class="block-chrome"
    :class="{ 'block-chrome--accented': accent !== null }"
    :style="accent === null ? undefined : { '--block-accent': accent }"
  >
    <figcaption class="block-chrome__head">
      <span class="block-chrome__label">
        <q-icon
          v-if="icon"
          :name="icon"
          size="16px"
        />
        {{ label }}
      </span>
      <span
        class="block-chrome__actions"
        data-export-exclude
      >
        <slot name="actions" />
      </span>
    </figcaption>
    <div class="block-chrome__body">
      <slot />
    </div>
  </figure>
</template>

<style scoped>
.block-chrome {
  overflow: hidden;
  margin: 12px 0;
  border: 1px solid var(--dp-border-faint);
  border-radius: 4px;
  background: var(--dp-surface);
}
.block-chrome__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 28px;
  padding: 0 4px 0 10px;
  border-bottom: 1px solid var(--dp-border-faint);
  background: var(--dp-chrome-raised);
}
.block-chrome__label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--dp-text-muted);
  font-size: 10px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.block-chrome--accented {
  border-color: color-mix(in srgb, var(--block-accent) 34%, var(--dp-border-faint));
  border-left: 3px solid var(--block-accent);
}
.block-chrome--accented .block-chrome__head {
  border-bottom-color: color-mix(in srgb, var(--block-accent) 24%, var(--dp-border-faint));
  background: color-mix(in srgb, var(--block-accent) 10%, var(--dp-surface));
}
.block-chrome--accented .block-chrome__label {
  color: var(--block-accent);
  font-weight: 600;
}
.block-chrome__actions {
  display: flex;
  align-items: center;
  gap: 2px;
}
.block-chrome__body {
  overflow-x: auto;
}
</style>
