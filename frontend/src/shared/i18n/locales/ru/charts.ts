import type { Messages } from "../en"

export const charts: Messages["charts"] = {
  read_failed: "Не удалось прочитать страницу для графика",
  page: {
    none: "Текущая страница · строки 0",
    range: "Текущая страница · строки {first}–{last}",
    more: "Следующие строки не учитываются.",
    bounded: "График строится только по этому ограниченному результату.",
  },
  no_data: "На этой странице нет значений для графика",
  no_measure: "На этой странице нет видимого числового столбца для графика",
  types: {
    line: "Линейный",
    bar: "Столбчатый",
    pie: "Круговой",
  },
  row: "Строка",
  other: "Прочее",
  numeric_on_page: "{name} (числовой на этой странице)",
  fields: {
    suggestion: "Предлагаемый вид",
    type: "Тип графика",
    label: "Подпись",
    value: "Значение",
    x: "Ось X",
    y: "Ось Y",
  },
  best_fit: "Подобрать",
  suggestions: {
    over: "{measure} вдоль {dimension}",
    by: "{measure} по {dimension}",
    share: "Доля {measure} по {dimension}",
  },
}
