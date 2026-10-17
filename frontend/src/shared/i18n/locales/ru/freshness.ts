import type { Messages } from "../en"

export const freshness: Messages["freshness"] = {
  live: "Онлайн",
  nothing: "ничего",
  read_now: "Прочитано из источника только что.",
  read_ago: "Прочитано из источника {age} назад.",
  keeps_as_source_says: "Подключение хранит ответы столько, сколько указывает источник.",
  keeps_nothing: "Подключение ничего не хранит: каждое чтение идёт в источник.",
  keeps_for: "Подключение хранит ответы в течение {window}.",
}
