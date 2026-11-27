import type { Messages } from "../en"

export const schema_form: Messages["schema_form"] = {
  hidden: "<скрыто>",
  show_password: "Показать пароль",
  hide_password: "Скрыть пароль",
  choose: "Выберите значение поля «{label}»",
  is_number: "Поле «{label}» принимает число",
  at_least: "Поле «{label}»: не меньше {n}",
  at_most: "Поле «{label}»: не больше {n}",
  required: "Заполните поле «{label}»",
  min_length:
    "Поле «{label}»: не меньше {n} символа | Поле «{label}»: не меньше {n} символов | Поле «{label}»: не меньше {n} символов | Поле «{label}»: не меньше {n} символа",
  from_file: "Прочитать «{label}» из файла",
  file_too_large: "Поле «{label}»: файл гораздо больше сертификата или ключа, выберите нужный файл",
  file_not_text: "Поле «{label}»: это не текстовый файл. Выберите файл PEM или JSON, а не двоичный",
  file_too_long: "Поле «{label}»: файл длиннее {n} символов — столько поле не принимает",
}
