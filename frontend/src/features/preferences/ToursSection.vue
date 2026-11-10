<script setup lang="ts">
import { useRouter } from "vue-router"

import { BASICS_TOUR } from "@/features/onboarding/basics"
import { useTourDone } from "@/features/onboarding/done"
import { startTour } from "@/features/onboarding/runner"
import { SHORT_TOURS } from "@/features/onboarding/shortTours"
import type { TourDefinition } from "@/features/onboarding/tour"
import { t } from "@/shared/i18n"
import { AppButton, AppSettingRow } from "@/shared/ui"

// Every tour, one row each (D355, D356): it runs over the workspace, so it
// starts there. A taken one says so on its button rather than vanish, since a
// tour is worth taking twice.
const TOURS: readonly TourDefinition[] = [BASICS_TOUR, ...SHORT_TOURS]

const router = useRouter()
const tours = useTourDone()

function take(tour: TourDefinition) {
  startTour(tour)
  void router.push("/")
}
</script>

<template>
  <div class="preferences-section">
    <AppSettingRow
      v-for="tour in TOURS"
      :key="tour.id"
      :title="tour.title()"
      :summary="tour.summary()"
    >
      <AppButton
        :variant="tours.isDone(tour.id) ? 'secondary' : 'primary'"
        :label="tours.isDone(tour.id) ? t('onboarding.tours.list.again') : t('onboarding.tours.list.take')"
        :data-testid="`preference-tour-${tour.id}`"
        @click="take(tour)"
      />
    </AppSettingRow>
  </div>
</template>

<style scoped>
.preferences-section {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
}
</style>
