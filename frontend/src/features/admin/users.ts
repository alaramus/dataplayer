import type { UserCreate, UserPublic, UserUpdate } from "@/client"

/**
 * The form behind the user dialog, and what it turns into.
 *
 * Plain functions rather than logic inside the component, so the rules that
 * matter — a password is required for a new account and optional for an
 * existing one, an unchanged field is not sent — are tested without mounting
 * anything.
 */
export interface UserForm {
  email: string
  fullName: string
  password: string
  isActive: boolean
  isSuperuser: boolean
}

export function emptyForm(): UserForm {
  return {
    email: "",
    fullName: "",
    password: "",
    isActive: true,
    isSuperuser: false,
  }
}

export function formOf(user: UserPublic): UserForm {
  return {
    email: user.email,
    fullName: user.full_name ?? "",
    // Never filled in from the server: a password is not something it sends,
    // and an empty box here means "keep the one there is".
    password: "",
    isActive: user.is_active ?? true,
    isSuperuser: user.is_superuser ?? false,
  }
}

/** The shortest password the server accepts. Stated once, next to the check
 * that uses it. */
export const MIN_PASSWORD = 8

/**
 * What is wrong with the form, by field. An empty object means nothing is.
 *
 * The same rules the server applies, checked here so that a typo does not cost
 * a round trip; the server still applies them, and its answer still wins.
 */
export function validate(form: UserForm, isNew: boolean): Record<string, string> {
  const errors: Record<string, string> = {}
  if (!/^\S+@\S+\.\S+$/.test(form.email)) {
    errors.email = "A valid email address is required"
  }
  const password = form.password
  if (isNew && password === "") {
    errors.password = "A password is required"
  } else if (password !== "" && password.length < MIN_PASSWORD) {
    errors.password = `At least ${MIN_PASSWORD} characters`
  }
  return errors
}

export function toCreate(form: UserForm): UserCreate {
  return {
    email: form.email,
    password: form.password,
    full_name: form.fullName === "" ? null : form.fullName,
    is_active: form.isActive,
    is_superuser: form.isSuperuser,
  }
}

/**
 * What to send for an existing account.
 *
 * An empty password box is left out entirely rather than sent as an empty
 * string: the field means "keep what is stored", and sending it would set a
 * password of no characters.
 */
export function toUpdate(form: UserForm): UserUpdate {
  const body: UserUpdate = {
    email: form.email,
    full_name: form.fullName === "" ? null : form.fullName,
    is_active: form.isActive,
    is_superuser: form.isSuperuser,
  }
  if (form.password !== "") body.password = form.password
  return body
}

/**
 * Why this account cannot be removed, or nothing.
 *
 * The server refuses a superuser deleting themselves; saying so before the
 * press is the same rule shown rather than explained after the fact.
 */
export function undeletableReason(user: UserPublic, currentUserId: string | null): string {
  return user.id === currentUserId ? "You cannot delete your own account" : ""
}
