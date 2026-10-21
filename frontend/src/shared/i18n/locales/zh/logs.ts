/** 服务器的日志（features/logs）。 */
import type { Messages } from "../en"

export const logs: Messages["logs"] = {
  logs: "日志",
  tooltip: "服务器的日志",
  levels: {
    all: "全部",
    warning: "警告和错误",
    error: "错误",
  },
  processes: {
    all: "所有进程",
    backend: "后端",
    metrics: "指标",
    search_keeper: "搜索索引",
  },
  only_superuser: "只有超级用户可以读取服务器的日志。",
  search: "搜索文本、ref 或路径",
  follow: "跟随",
  reload: "重新读取日志",
  read_failed: "无法读取日志",
  not_kept: "此服务器不保留日志文件。设置 LOG_DIR 即可保留；在此之前，日志会输出到服务器的标准输出。",
  nothing: "日志中没有匹配的内容。",
  ref: "ref {ref}",
  copy: "复制此条目",
  copied: "已复制",
  copy_refused: "浏览器不允许复制",
  older: "更早的条目",
}
