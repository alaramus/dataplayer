/**
 * The shared UI kit: one import path for every screen.
 *
 * What belongs here is anything with a choice of appearance. Layout primitives
 * with a single consumer, and elements with nothing to decide, stay as Quasar
 * components — see docs/superpowers/specs/2026-08-22-shared-ui-kit-design.md.
 */
export { default as AppActions } from "./AppActions.vue"
export { default as AppBadge } from "./AppBadge.vue"
export { default as AppBanner } from "./AppBanner.vue"
export { default as AppButton } from "./AppButton.vue"
export { default as AppCard } from "./AppCard.vue"
export { default as AppCheckbox } from "./AppCheckbox.vue"
export { default as AppDialog } from "./AppDialog.vue"
export { default as AppEmptyState } from "./AppEmptyState.vue"
export { default as AppFileInput } from "./AppFileInput.vue"
export { default as AppIconButton } from "./AppIconButton.vue"
export { default as AppInput } from "./AppInput.vue"
export { default as AppLayout } from "./AppLayout.vue"
export { default as AppMenu } from "./AppMenu.vue"
export type { MenuItem } from "./AppMenu.vue"
export { default as AppNumberInput } from "./AppNumberInput.vue"
export { default as AppPageHeader } from "./AppPageHeader.vue"
export { default as AppSection } from "./AppSection.vue"
export { default as AppSelect } from "./AppSelect.vue"
export { default as AppSpinner } from "./AppSpinner.vue"
export { default as AppTable } from "./AppTable.vue"
export { default as AppThemeToggle } from "./AppThemeToggle.vue"
export { default as AppToggle } from "./AppToggle.vue"
export { default as AppTooltip } from "./AppTooltip.vue"
export { default as AppTree } from "./AppTree.vue"

export { useConfirm } from "./useConfirm"
export type { ConfirmRequest } from "./useConfirm"
export { useToast } from "./useToast"
export type { Toast } from "./useToast"

export { badgeColor, bannerLook, buttonLook, panelStyle, SCROLL_MAX_HEIGHT } from "./tokens"
export type { BannerLook, ButtonLook, ButtonVariant, PanelSize, PanelStyle, Tone } from "./tokens"
