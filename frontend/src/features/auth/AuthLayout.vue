<script setup lang="ts">
import { t } from "@/shared/i18n"

/** The product's name, which no language translates. */
const PRODUCT = "DataPlayer"
</script>

<template>
  <!-- The page somebody meets before they have a session: what the product is
       on one half, the form on the other. Signing in and choosing a first
       password are the same moment for a new person, so they look alike. -->
  <div class="auth-layout">
    <!-- Decoration, so the form is the page's one landmark. -->
    <section
      class="auth-welcome"
      aria-hidden="true"
    >
      <div class="auth-welcome-body">
        <img
          class="auth-logo"
          src="/icons/logodp.svg"
          alt=""
        >
        <div class="auth-product">
          {{ PRODUCT }}
        </div>
        <p class="auth-tagline">
          {{ t('auth.welcome_tagline') }}
        </p>
      </div>
    </section>
    <main class="auth-side">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.auth-layout { min-height: 100vh; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); background: var(--dp-surface); }
.auth-welcome { display: grid; place-items: center; padding: var(--dp-space-5); background: linear-gradient(160deg, var(--dp-chrome) 0%, var(--dp-chrome-raised) 100%); border-inline-end: 1px solid var(--dp-border); }
.auth-welcome-body { display: flex; flex-direction: column; align-items: center; gap: var(--dp-space-3); max-width: var(--dp-width-text); text-align: center; }
.auth-logo { width: var(--dp-width-name); max-width: 50%; height: auto; margin-bottom: var(--dp-space-3); }
.auth-product { font-size: var(--dp-font-size-display); font-weight: 600; color: var(--dp-text); }
.auth-tagline { margin: 0; font-size: var(--dp-font-size-lg); color: var(--dp-text-muted); }
.auth-side { display: grid; place-items: center; padding: var(--dp-space-5); }
</style>
