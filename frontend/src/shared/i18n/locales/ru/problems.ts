import type { ProblemCode } from "@/shared/i18n/problems"

/** The server's refusals in Russian, by code (D225). */
export const problems: Record<ProblemCode, string> = {
  "auth.wrong_credentials": "Неверный адрес эл. почты или пароль",
  "auth.inactive_user": "Учётная запись отключена",
  "auth.invalid_token": "Ссылка недействительна",
  "auth.not_signed_in": "Не удалось подтвердить вход",
  "auth.not_enough_privileges": "Недостаточно прав",
  "auth.no_user_with_email": "Пользователя с таким адресом эл. почты нет",
  "users.email_taken": "Пользователь с таким адресом эл. почты уже есть",
  "users.not_found": "Пользователь не найден",
  "users.wrong_password": "Неверный пароль",
  "users.same_password": "Новый пароль должен отличаться от текущего",
  "users.superuser_cannot_delete_self": "Суперпользователь не может удалить сам себя",
}
