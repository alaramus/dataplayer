import type { Messages } from "../en"

export const common: Messages["common"] = {
  back_to_workspace: "Вернуться в рабочую область",
}

export const language: Messages["language"] = {
  label: "Язык",
  browser: "Язык браузера",
  browser_hint: "Язык, который запрашивает этот браузер, или английский",
}

export const auth: Messages["auth"] = {
  sign_in: "Войти",
  email: "Эл. почта",
  password: "Пароль",
  email_required: "Укажите адрес эл. почты",
  password_required: "Укажите пароль",
  checking_server: "Проверка сервера…",
  retry_connection: "Повторить подключение",
  sign_in_failed: "Не удалось войти. Проверьте адрес эл. почты и пароль.",
  welcome_tagline: "Одно место для всех ваших источников данных",
  set_password: {
    title: "Задайте пароль",
    for_whom: "Для {email}",
    new: "Новый пароль",
    repeat: "Повторите пароль",
    too_short: "Не меньше {n} символа | Не меньше {n} символов | Не меньше {n} символов | Не меньше {n} символа",
    mismatch: "Пароли не совпадают",
    submit: "Задать пароль",
    done: "Пароль задан. Войдите с ним.",
    checking: "Проверяю ссылку…",
    invalid: "Эта ссылка больше не работает: ею уже воспользовались, её срок истёк или выдана новая. Попросите администратора прислать новую.",
    to_sign_in: "Перейти ко входу",
  },
}

export const theme: Messages["theme"] = {
  label: "Тема",
  light: "Светлая",
  paper_light: "Светлая бумага",
  paper_light_hint: "Тёплая светлая бумага с бронзовым акцентом",
  dark: "Тёмная",
  paper: "Тёмная бумага",
  paper_hint: "Тёплая тёмная бумага с бронзовым акцентом",
  midnight: "Полночь",
  midnight_hint: "Самая тёмная: почти чёрный синий с ледяным голубым акцентом",
  dark_blue: "Тёмно-синяя",
  dark_blue_hint: "Насыщенный тёмно-синий с бирюзовым акцентом",
  dark_purple: "Тёмно-фиолетовая",
  dark_purple_hint: "Фиолетовый неон с розовым и бирюзовым акцентами",
  system: "Как в системе",
  system_hint: "Светлая или тёмная — вслед за операционной системой",
  switch_to: "Переключить на «{theme}»",
}
