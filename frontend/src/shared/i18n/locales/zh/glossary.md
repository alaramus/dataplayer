# Chinese: terms and style

One word for one thing, across every screen. Add a term here before using a
second word for it.

## Style

- Simplified Chinese (`zh`), Quasar's `zh-CN` pack, ECharts' `ZH` locale.
- Sentence case does not apply; write natural Chinese. A label is short and
  noun-like: “连接”, “保存”, “取消”, “删除”.
- A button or menu item is an action, usually a verb: “保存”, “删除”, “打开”,
  “取消”. Cancel is “取消”.
- Address the reader impersonally where possible: “无法保存文件”, not
  “您无法保存文件”. Use “你” only where a full sentence must address one person,
  and keep it consistent within a message.
- Punctuation is full-width: “，”, “。”, “：”, “；”, “（”, “）”. Quotes are “…”.
  A dash is “—”, an ellipsis is “……”.
- Keep one space between Latin text and Chinese where it aids reading:
  “PostgreSQL 连接”, “CSV 文件”, “{n} 行”.
- Names a person typed (a table, a connection) stay as they are, in quotes.
- Product and protocol names stay in Latin: PostgreSQL, TimescaleDB, Redis,
  SSH, S3, SQL, CSV, JSON, DuckDB, Docker.
- Do not translate code, identifiers, SQL, key names, enum values, or a
  `{placeholder}`. A placeholder is kept exactly: `{name}`, `{count}`, `{table}`.
- Chinese has one plural form. An English message written `one | other` becomes
  one Chinese sentence, without `|`: “{n} 个表”.
- Never write a bare `@` or `$` in a vue-i18n message.

## Terms

| English | 中文 |
| --- | --- |
| connection | 连接 |
| source | 数据源 |
| workspace | 工作区 |
| catalog | 目录 |
| node | 节点 |
| panel | 面板 |
| tab | 标签页 |
| tab group | 标签组 |
| rail (tool rail) | 工具栏 |
| bottom panel | 底部面板 |
| pair (two catalogs side by side) | 双目录 |
| window | 窗口 |
| table | 表 |
| view | 视图 |
| materialized view | 物化视图 |
| relation | 关系 |
| schema | 模式 |
| database | 数据库 |
| column | 列 |
| row | 行 |
| index | 索引 |
| constraint | 约束 |
| primary key | 主键 |
| foreign key | 外键 |
| reference (declared) | 引用 |
| declared reference | 声明引用 |
| function | 函数 |
| sequence | 序列 |
| trigger | 触发器 |
| extension | 扩展 |
| hypertable | 超表 |
| chunk | 数据块 |
| key (Redis) | 键 |
| key space | 键空间 |
| file storage | 文件存储 |
| query | 查询 |
| result | 结果 |
| row view | 行视图 |
| action | 操作 |
| capability | 能力 |
| download | 下载 |
| export | 导出 |
| import | 导入 |
| paste | 粘贴 |
| copy | 复制 |
| transfer | 传输 |
| pipeline | 流水线 |
| link (pipeline) | 连线 |
| run | 运行 |
| job | 任务 |
| step | 步骤 |
| dashboard | 仪表盘 |
| widget | 小组件 |
| metric | 指标 |
| agent | 智能体 |
| chat | 对话 |
| message | 消息 |
| prompt | 提示词 |
| search | 搜索 |
| search index | 搜索索引 |
| share | 分享 |
| link (share) | 链接 |
| access | 访问权限 |
| grant | 授权 |
| user | 用户 |
| account | 账户 |
| superuser | 超级用户 |
| preference | 偏好设置 |
| theme | 主题 |
| terminal | 终端 |
| server | 服务器 |
| service | 服务 |
| template | 模板 |
| backup | 备份 |
| report | 报告 |
| notification | 通知 |
| onboarding | 新手引导 |
| guide | 用户指南 |
| freshness | 新鲜度 |
| grid | 表格 |
| record | 记录 |
| content | 内容 |
| document | 文档 |
| archive | 压缩包 |
| relationship | 关系 |
| schema form | 表单 |
| source operation | 数据源操作 |
| refresh | 刷新 |
| save | 保存 |
| delete | 删除 |
| cancel | 取消 |
| close | 关闭 |
| open | 打开 |
| settings | 设置 |
| preferences | 偏好设置 |
