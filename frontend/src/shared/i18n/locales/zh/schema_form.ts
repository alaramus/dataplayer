/** 由 JSON 模式绘制的表单（shared/SchemaForm）。 */
import type { Messages } from "../en"

export const schema_form: Messages["schema_form"] = {
  hidden: "<已隐藏>",
  show_password: "显示密码",
  hide_password: "隐藏密码",
  choose: "选择 {label}",
  is_number: "{label} 是一个数字",
  at_least: "{label} 至少为 {n}",
  at_most: "{label} 至多为 {n}",
  required: "{label} 为必填项",
  min_length: "{label} 至少需要 {n} 个字符",
  from_file: "从文件读取 {label}",
  file_too_large: "{label}：此文件远大于证书或密钥，请选择该文件本身",
  file_not_text: "{label}：此文件不是文本。请选择 PEM 或 JSON 文件，而不是二进制文件",
  file_too_long: "{label}：文件包含超过 {n} 个字符，超出该字段的上限",
}
