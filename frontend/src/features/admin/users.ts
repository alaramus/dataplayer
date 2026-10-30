import type { UserInvite, UserPublic, UserUpdate } from "@/client"
import { t } from "@/shared/i18n"

/**
 * The form behind the user dialog, and what it turns into.
 *
 * Plain functions rather than logic inside the component, so the rules that
 * matter are tested without mounting anything. There is no password here: a
 * new account chooses its own through the link it is given, and an existing
 * one is reset by issuing another.
 */
export interface UserForm {
  email: string
  fullName: string
  isActive: boolean
  isSuperuser: boolean
}

export function emptyForm(): UserForm {
  return {
    email: "",
    fullName: "",
    isActive: true,
    isSuperuser: false,
  }
}

export function formOf(user: UserPublic): UserForm {
  return {
    email: user.email,
    fullName: user.full_name ?? "",
    isActive: user.is_active ?? true,
    isSuperuser: user.is_superuser ?? false,
  }
}

/**
 * What is wrong with the form, by field. An empty object means nothing is.
 *
 * The same rule the server applies, checked here so that a typo does not cost
 * a round trip; the server still applies it, and its answer still wins.
 */
export function validate(form: UserForm): Record<string, string> {
  const errors: Record<string, string> = {}
  if (!/^\S+@\S+\.\S+$/.test(form.email)) {
    errors.email = t("admin.users.email_invalid")
  }
  return errors
}

export function toCreate(form: UserForm): UserInvite {
  return {
    email: form.email,
    full_name: form.fullName === "" ? null : form.fullName,
    is_active: form.isActive,
    is_superuser: form.isSuperuser,
  }
}

export function toUpdate(form: UserForm): UserUpdate {
  return {
    email: form.email,
    full_name: form.fullName === "" ? null : form.fullName,
    is_active: form.isActive,
    is_superuser: form.isSuperuser,
  }
}

/**
 * Why this account cannot be removed, or nothing.
 *
 * The server refuses a superuser deleting themselves; saying so before the
 * press is the same rule shown rather than explained after the fact.
 */
export function undeletableReason(user: UserPublic, currentUserId: string | null): string {
  return user.id === currentUserId ? t("admin.users.cannot_delete_self") : ""
}
