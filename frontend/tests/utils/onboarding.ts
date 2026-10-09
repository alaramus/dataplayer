import type { APIRequestContext } from "@playwright/test"

/**
 * Say on the account whether the welcome tour was seen (`welcome_tour_done`).
 *
 * A preference of the account, so it is set through the API before the
 * browser signs in: the tour opens as soon as the workspace reads it, and
 * every scenario but the tour's own arrives with it already seen.
 */
export async function setTourSeen(
  request: APIRequestContext,
  email: string,
  password: string,
  seen = true
): Promise<void> {
  const api = `${process.env.VITE_API_URL ?? "http://localhost:8000"}/api/v1`
  const login = await request.post(`${api}/login/access-token`, {
    form: { username: email, password },
  })
  if (!login.ok()) throw new Error(`Could not sign ${email} in: ${String(login.status())}`)
  const { access_token: token } = (await login.json()) as { access_token: string }
  const saved = await request.patch(`${api}/users/me/preferences`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { welcome_tour_done: seen },
  })
  if (!saved.ok()) throw new Error(`Could not mark the tour for ${email}: ${String(saved.status())}`)
}
