<script setup lang="ts">
import { computed, ref } from "vue"

import type { ScheduleSettings } from "@/client"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppCheckbox,
  AppForm,
  AppFormControl,
  AppIconButton,
  AppInput,
  AppNumberInput,
  AppRadioGroup,
  AppSelect,
  AppToggle,
  appIcons,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { useSaveSchedule } from "./api"
import { browserZone, firstSettings, intervalParts, MAX_TIMES, minutesOf } from "./schedule"
import type { IntervalUnit } from "./schedule"

/**
 * When a pipeline runs by itself (D179): every so long, or at times of the
 * day on chosen days, in this browser's clock. Kept as a whole on Save.
 */
const props = defineProps<{
  pipelineId: string
  pipelineName: string
  settings: ScheduleSettings | null | undefined
}>()

const emit = defineEmits<{ close: [] }>()

const saving = useSaveSchedule()
const zone = browserZone()
const start = props.settings ?? firstSettings(zone)
const enabled = ref(start.enabled ?? false)
const kind = ref<string>(start.kind ?? "times")
const interval = intervalParts(start.every_minutes ?? 60)
const count = ref<number | null>(interval.count)
const unit = ref<IntervalUnit>(interval.unit)
const times = ref<string[]>([...(start.times ?? ["03:00"])])
const days = ref<Set<number>>(new Set(start.days ?? []))
const failure = ref("")

const KINDS = [
  { label: "Every so long", value: "interval", description: "Counted from when it is saved" },
  { label: "At times of the day", value: "times", description: "On the days ticked below" },
]
const UNITS = [
  { label: "minutes", value: "minutes" },
  { label: "hours", value: "hours" },
  { label: "days", value: "days" },
]
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

const chosen = computed<ScheduleSettings>(() => ({
  enabled: enabled.value,
  kind: kind.value === "interval" ? "interval" : "times",
  every_minutes: minutesOf(count.value ?? 0, unit.value),
  times: times.value.filter((time) => time !== ""),
  days: [...days.value].sort((a, b) => a - b),
  // Saved in this browser's clock, whatever it was set in before.
  time_zone: zone,
}))

function toggleDay(day: number, on: boolean) {
  const next = new Set(days.value)
  if (on) next.add(day)
  else next.delete(day)
  days.value = next
}

function setTime(index: number, value: string | number | null) {
  times.value = times.value.map((time, at) => (at === index ? String(value ?? "") : time))
}

async function save() {
  failure.value = ""
  try {
    await saving.mutateAsync({ pipelineId: props.pipelineId, settings: chosen.value })
    emit("close")
  } catch (cause) {
    failure.value = messageOf(cause, "The schedule could not be kept")
  }
}
</script>

<template>
  <WindowDialog
    :model-value="true"
    title="Schedule"
    :subtitle="`When ${pipelineName} runs by itself`"
    size="form"
    sizing="stable"
    data-testid="schedule-window"
    @update:model-value="emit('close')"
  >
    <AppForm
      layout="section"
      labels="above"
    >
      <AppToggle
        v-model="enabled"
        label="Run by itself"
        data-testid="schedule-enabled"
      />
      <AppRadioGroup
        v-model="kind"
        :options="KINDS"
        label="When"
        data-testid="schedule-kind"
      />
      <template v-if="kind === 'interval'">
        <AppNumberInput
          v-model="count"
          label="Every"
          data-testid="schedule-every"
        />
        <AppSelect
          v-model="unit"
          :options="UNITS"
          label="Of"
          data-testid="schedule-unit"
        />
      </template>
      <template v-else>
        <!-- Fields of the form like any other, so "At" stands in the label
             column; inside a form control each one was set in twice. -->
        <AppInput
          v-for="(time, index) in times"
          :key="index"
          :model-value="time"
          type="time"
          :label="index === 0 ? 'At' : 'And at'"
          :data-testid="`schedule-time-${index}`"
          @update:model-value="setTime(index, $event)"
        >
          <template
            v-if="times.length > 1"
            #after
          >
            <AppIconButton
              :icon="appIcons.close"
              tooltip="Remove this time"
              :data-testid="`schedule-time-remove-${index}`"
              @click="times = times.filter((_, at) => at !== index)"
            />
          </template>
        </AppInput>
        <AppFormControl>
          <AppButton
            variant="quiet"
            size="sm"
            :icon="appIcons.add"
            label="Add a time"
            :disable="times.length >= MAX_TIMES"
            data-testid="schedule-add-time"
            @click="times = [...times, '12:00']"
          />
        </AppFormControl>
        <AppFormControl>
          <div class="schedule-window__days">
            <AppCheckbox
              v-for="(day, index) in DAYS"
              :key="day"
              :model-value="days.has(index)"
              class="schedule-window__day"
              :label="day"
              dense
              :data-testid="`schedule-day-${index}`"
              @update:model-value="toggleDay(index, $event)"
            />
          </div>
        </AppFormControl>
      </template>
      <AppFormControl>
        <span class="schedule-window__zone">Times are this browser's clock: {{ zone }}</span>
      </AppFormControl>
      <AppBanner
        v-if="failure"
        tone="error"
      >
        {{ failure }}
      </AppBanner>
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="emit('close')"
      />
      <AppButton
        label="Save"
        :loading="saving.isPending.value"
        data-testid="schedule-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.schedule-window__days {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--dp-space-2);
}
.schedule-window__zone {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}
</style>
