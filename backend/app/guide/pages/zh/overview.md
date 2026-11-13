# DataPlayer 概览

DataPlayer 把你使用的数据源连接起来——数据库、文件存储、消息队列、通过 SSH 访问的服务器等——让你在同一个地方读取和修改它们。本页说明各项内容的位置；每个部分都有自己的页面。

## 四个空间

左侧栏顶部的切换开关决定屏幕上显示什么：

- **数据**：你的连接、它们的目录，以及从中打开的表、文件和查询。参见[工作区](workspace.md)和[连接](connections.md)。
- **流水线**：在画布上排列的连接，以及在它们之间复制行和文件的链接，可手动运行，也可按计划运行。参见[流水线](pipelines.md)。
- **仪表盘**：由代理和连接上报、随时间绘制的指标。参见[仪表盘](dashboards.md)。
- **AI**：与代理的对话。代理通过同样的连接读取和修改你的数据。参见[AI 代理](assistant.md)。

切换空间时，已打开的内容会保留：返回 **数据** 时，标签页与离开时相同。

## 周边区域

- **顶栏**包含搜索框，可查找连接、表、文件、已保存的查询、流水线、仪表盘、对话以及本指南的页面。Ctrl+K（Mac 上为 ⌘K）把光标移到搜索框。参见[搜索](search.md)。
- **用户菜单**位于右上角，可打开 **偏好设置**、管理员的 **管理**，以及 **退出登录**。参见[偏好设置与账户](preferences.md)。
- **两侧的栏**以图标形式放置工具：左上角是空间切换开关和 **快速对话**；左下角是 **服务**、**终端**、**查询** 和 **搜索索引**；右上角是保存和打开标签组。工具可以拖到同一栏的其他位置，或拖到另一栏。
- **底部面板**为 **服务**、**终端**、**查询**、**搜索索引** 打开；管理员还可打开 **日志**。参见[服务与终端](services.md)。
- **活动铃铛**位于右下角，打开 **活动**：显示等待你回应的事项、正在运行的任务以及最近发生的事件。

## 相关内容的去处

- 某一类数据源——其专属页面：[PostgreSQL](source-postgres.md)、[MySQL 与 MariaDB](source-mysql.md)、[SQLite](source-sqlite.md)、[ClickHouse](source-clickhouse.md)、[Cassandra 与 ScyllaDB](source-cassandra.md)、[MongoDB](source-mongodb.md)、[Redis](source-redis.md)、[ZooKeeper](source-zookeeper.md)、[Kafka](source-kafka.md)、[RabbitMQ](source-rabbitmq.md)、[Binance](source-binance.md)、[文件](source-file.md)和 [SSH](source-ssh.md)。读取、编辑行、修改结构、SQL 控制台和报表均在对应数据源的页面中说明；
- 添加、共享和设置连接——[连接](connections.md)；
- 列、标签页、窗口和标签组——[工作区](workspace.md)；
- 按计划移动数据——[流水线](pipelines.md)；
- 随时间变化的指标和图表——[仪表盘](dashboards.md)；
- 代理、快速对话以及连接外部 AI 代理——[AI 代理](assistant.md)；
- 在此启动的服务、终端和备份——[服务与终端](services.md)。
