"""TimescaleDB 的操作和报告所写入的内容，简体中文（D226）。

术语遵循界面词汇表；TimescaleDB 自身的函数名和选项名保持不变。
"""

MESSAGES: dict[str, str] = {
    # 时长，按预览中的显示方式。
    "{amount} second": "{amount} 秒",
    "{amount} seconds": "{amount} 秒",
    "{amount} minute": "{amount} 分钟",
    "{amount} minutes": "{amount} 分钟",
    "{amount} hour": "{amount} 小时",
    "{amount} hours": "{amount} 小时",
    "{amount} day": "{amount} 天",
    "{amount} days": "{amount} 天",
    "{amount} week": "{amount} 周",
    "{amount} weeks": "{amount} 周",
    "{amount} month": "{amount} 个月",
    "{amount} months": "{amount} 个月",
    "{amount} year": "{amount} 年",
    "{amount} years": "{amount} 年",
    "{amount} value": "{amount} 个值",
    "{amount} values": "{amount} 个值",
    # 报告。
    "Hypertables": "超表",
    "Hypertable owners, dimension/chunk counts and compression configuration": (
        "超表所有者、维度与数据块数量及压缩配置"
    ),
    "Continuous aggregates": "连续聚合",
    "Aggregate owners, source/materialization identities and configuration": (
        "聚合所有者、源与物化标识及配置"
    ),
    "Chunks": "数据块",
    "Chunk identities, primary-dimension boundaries and compression status": (
        "数据块标识、主维度边界及压缩状态"
    ),
    "Dimensions": "维度",
    "Time, integer and space dimensions of each hypertable": (
        "每个超表的时间、整数与空间维度"
    ),
    "Policies and jobs": "策略与任务",
    "Native TimescaleDB jobs, including policies and their schedules": (
        "TimescaleDB 原生任务，包括策略及其计划"
    ),
    "Job statistics": "任务统计",
    "Recorded native job runs, outcomes and counters; unrun jobs may be absent": (
        "已记录的原生任务运行、结果与计数器；未运行过的任务可能不在其中"
    ),
    "Detached chunks": "已分离数据块",
    "Tables named like a chunk that no hypertable holds; Attach chunk takes one back": (
        "名称类似数据块但不属于任何超表的表；“附加数据块”可将其收回"
    ),
    "This report cannot be inspected by this connection": "此连接无法查看该报告",
    "The installed TimescaleDB lacks the public API for this view": (
        "已安装的 TimescaleDB 缺少此视图所需的公共 API"
    ),
    # 探测 TimescaleDB。
    "TimescaleDB is not installed on this database": "此数据库未安装 TimescaleDB",
    "This source has no usable TimescaleDB API": "此数据源没有可用的 TimescaleDB API",
    "This connection may not inspect installed extensions": (
        "此连接无权查看已安装的扩展"
    ),
    "Installed extensions could not be inspected": "无法查看已安装的扩展",
    "The installed TimescaleDB version could not be read": "无法读取已安装的 TimescaleDB 版本",
    "TimescaleDB extension metadata could not be read": "无法读取 TimescaleDB 扩展元数据",
    "This TimescaleDB major version is not supported": "不支持此 TimescaleDB 主版本",
    "This connection may not inspect TimescaleDB metadata": "此连接无权查看 TimescaleDB 元数据",
    "TimescaleDB metadata could not be inspected": "无法查看 TimescaleDB 元数据",
    "The installed version lacks the supported inspection API": (
        "已安装的版本缺少受支持的查看 API"
    ),
    "TimescaleDB action vocabulary could not be inspected": "无法确定可用的 TimescaleDB 操作",
    "The TimescaleDB {routine} API is not usable by this connection": (
        "此连接无法使用 TimescaleDB {routine} API"
    ),
    "The TimescaleDB {type} type is not usable by this connection": (
        "此连接无法使用 TimescaleDB {type} 类型"
    ),
    "This connection may not lock TimescaleDB public metadata": (
        "此连接无权锁定 TimescaleDB 公共元数据"
    ),
    # 一个关系的 TimescaleDB 事实。
    "TimescaleDB metadata no longer identifies this relation uniquely": (
        "TimescaleDB 元数据已无法唯一标识此关系"
    ),
    "TimescaleDB metadata inspection timed out": "查看 TimescaleDB 元数据超时",
    "TimescaleDB metadata could not be inspected safely": "无法安全地查看 TimescaleDB 元数据",
    "TimescaleDB size inspection timed out": "确定 TimescaleDB 大小超时",
    "TimescaleDB compression inspection timed out": "读取 TimescaleDB 压缩统计信息超时",
    "TimescaleDB size could not be inspected safely": "无法安全地确定 TimescaleDB 大小",
    "TimescaleDB compression statistics could not be inspected safely": (
        "无法安全地读取 TimescaleDB 压缩统计信息"
    ),
    # 操作所针对的表。
    "Choose one user hypertable": "请选择一个用户超表",
    "Choose one user continuous aggregate": "请选择一个用户连续聚合",
    "Choose an owned hypertable": "请选择你拥有的超表",
    "Choose an owned hypertable with one time dimension": (
        "请选择你拥有的、带一个时间维度的超表"
    ),
    "Choose an owned hypertable partitioned by time": (
        "请选择你拥有的、按时间分区的超表"
    ),
    "Choose an owned continuous aggregate": "请选择你拥有的连续聚合",
    "Only timestamp and date dimensions are supported here": "此处仅支持 timestamp 和 date 维度",
    "Only a hypertable with one range dimension is maintained here": (
        "此处仅维护带一个范围维度的超表"
    ),
    "Only timestamp, date and integer dimensions are supported here": (
        "此处仅支持 timestamp、date 和整数维度"
    ),
    "Only aggregates over timestamp and date dimensions are supported here": (
        "此处仅支持基于 timestamp 和 date 维度的聚合"
    ),
    # 查看并应用计划。
    "The operation plan changed; review it again": "操作计划已更改；请重新查看",
    "Validation timed out; review the plan again": "验证超时；请重新查看计划",
    "The source changed or is busy; review the plan again": "数据源已更改或正忙；请重新查看计划",
    "The change could not be confirmed; reload the source before reviewing again": (
        "无法确认更改；请重新加载数据源后再查看"
    ),
    "The change ran past its {seconds} seconds and was rolled back": (
        "更改超出了 {seconds} 秒的时限，已回滚"
    ),
    "This connection may not make this change or lock its metadata": (
        "此连接无权进行此更改或锁定其元数据"
    ),
    "The source refused the change": "数据源拒绝了此更改",
    "Runs in Activity, one such job per connection at a time; access is checked again before every chunk": (
        "在“活动”中运行，每个连接同时只能有一个此类任务；每个数据块处理前都会重新检查访问权限"
    ),
    "Runs in Activity, one such job per connection at a time; access is checked again before every unit": (
        "在“活动”中运行，每个连接同时只能有一个此类任务；每个单元处理前都会重新检查访问权限"
    ),
    # 预览中的共用行。
    "Time dimension: {column}": "时间维度：{column}",
    "Unit": "单位",
    "{chunk}: {start} to {end}": "{chunk}：{start} 至 {end}",
    "…and {count} more": "……以及另外 {count} 个",
    "Whole chunks from the earliest chunk to {end}": "从最早的数据块到 {end} 的完整数据块",
    "Whole chunks from {start} to {end}": "从 {start} 到 {end} 的完整数据块",
    "Give an instant with its time zone, such as 2026-01-15T00:00:00Z, or a whole number": (
        "请给出带时区的时间点，例如 2026-01-15T00:00:00Z，或给出整数"
    ),
    "The number is outside the range of a bigint": "该数字超出 bigint 的范围",
    "Both ends are instants, or both are numbers": "两端必须都是时间点，或都是数字",
    "The range must start before it ends": "范围的起点必须早于终点",
    "The window must start before it ends": "窗口的起点必须早于终点",
    "Chunks ending at or before": "结束时间不晚于",
    "With its time zone; only chunks lying entirely inside the window are chosen": (
        "需带时区；仅选择完全位于窗口内的数据块"
    ),
    "and starting at or after": "且开始时间不早于",
    "Leave empty for every earlier chunk": "留空表示所有更早的数据块",
    # 数据块间隔。
    "Change chunk interval": "更改数据块间隔",
    "Review the interval plan before applying it": "应用前请查看间隔计划",
    "Future chunk interval changed; existing chunks were not repartitioned": (
        "未来数据块的间隔已更改；现有数据块未重新分区"
    ),
    "Change the future chunk interval for {target}": "更改 {target} 的未来数据块间隔",
    "Current interval: {interval}": "当前间隔：{interval}",
    "Requested interval: {interval}": "请求的间隔：{interval}",
    "Only future chunks use the new interval; existing chunks are not repartitioned": (
        "只有未来数据块使用新间隔；现有数据块不会重新分区"
    ),
    "Briefly locks TimescaleDB metadata across this database; new chunk creation may wait": (
        "会短暂锁定整个数据库中的 TimescaleDB 元数据；新建数据块可能需等待"
    ),
    "TimescaleDB interval metadata could not be inspected safely": (
        "无法安全地查看 TimescaleDB 间隔元数据"
    ),
    "TimescaleDB interval planning timed out": "规划 TimescaleDB 间隔超时",
    "Calendar chunk intervals are not supported by this strategy": (
        "此策略不支持按日历划分的数据块间隔"
    ),
    "Date dimensions require whole days or weeks": "date 维度要求整数天或整数周",
    "Interval validation timed out; review the plan again": "间隔验证超时；请重新查看计划",
    "This connection may not change the interval or lock its metadata": (
        "此连接无权更改间隔或锁定其元数据"
    ),
    "The source refused the interval change": "数据源拒绝了间隔更改",
    "The interval change could not be confirmed; reload the source before reviewing again": (
        "无法确认间隔更改；请重新加载数据源后再查看"
    ),
    # 保留策略与压缩策略。
    "Set retention policy": "设置保留策略",
    "Remove retention policy": "删除保留策略",
    "Set compression policy": "设置压缩策略",
    "Remove compression policy": "删除压缩策略",
    "TimescaleDB will keep dropping old chunks by itself, even after this session ends. Set this policy?": (
        "即使此会话结束，TimescaleDB 也会继续自行删除旧数据块。要设置此策略吗？"
    ),
    "Drop chunks older than": "删除早于以下时间的数据块",
    "Compress chunks older than": "压缩早于以下时间的数据块",
    "Set the retention policy for {target}": "为 {target} 设置保留策略",
    "Remove the retention policy from {target}": "删除 {target} 的保留策略",
    "Set the compression policy for {target}": "为 {target} 设置压缩策略",
    "Remove the compression policy from {target}": "删除 {target} 的压缩策略",
    "No retention policy exists yet": "尚无保留策略",
    "No compression policy exists yet": "尚无压缩策略",
    "older than {age}": "早于 {age}",
    "created more than {age} ago": "创建于 {age} 以前",
    "Removes job {job}, which drops chunks {chunks}": "删除任务 {job}，该任务会删除数据块 {chunks}",
    "Replaces job {job}, which drops chunks {chunks}": "替换任务 {job}，该任务会删除数据块 {chunks}",
    "Removes job {job}, which compresses chunks {chunks}": "删除任务 {job}，该任务会压缩数据块 {chunks}",
    "Replaces job {job}, which compresses chunks {chunks}": "替换任务 {job}，该任务会压缩数据块 {chunks}",
    "The current policy runs every {every}; its replacement uses TimescaleDB's default schedule": (
        "当前策略每 {every} 运行一次；其替代策略使用 TimescaleDB 的默认计划"
    ),
    "New policy: drop chunks older than {age}": "新策略：删除早于 {age} 的数据块",
    "New policy: compress chunks older than {age}": "新策略：压缩早于 {age} 的数据块",
    "TimescaleDB keeps dropping whole chunks older than this on its own schedule, after this session ends": (
        "此会话结束后，TimescaleDB 仍会按自己的计划删除早于此时限的完整数据块"
    ),
    "TimescaleDB stops dropping old chunks automatically; chunks already dropped do not return": (
        "TimescaleDB 将停止自动删除旧数据块；已删除的数据块不会恢复"
    ),
    "TimescaleDB keeps compressing chunks older than this on its own schedule; compressed chunks stay readable": (
        "TimescaleDB 会按自己的计划继续压缩早于此时限的数据块；压缩后的数据块仍可读取"
    ),
    "TimescaleDB stops compressing chunks automatically; chunks already compressed stay compressed": (
        "TimescaleDB 将停止自动压缩数据块；已压缩的数据块保持压缩状态"
    ),
    "Other policy changes made here in this database wait until it commits, and so may a policy run starting meanwhile": (
        "在此数据库中进行的其他策略更改会等待提交，其间启动的策略运行也可能需要等待"
    ),
    "Review the retention policy plan before applying it": (
        "应用前请查看保留策略计划"
    ),
    "Review the compression policy plan before applying it": (
        "应用前请查看压缩策略计划"
    ),
    "Retention policy set: TimescaleDB drops chunks older than {age} on its own schedule": (
        "保留策略已设置：TimescaleDB 会按自己的计划删除早于 {age} 的数据块"
    ),
    "Retention policy removed; TimescaleDB no longer drops old chunks automatically": (
        "保留策略已删除；TimescaleDB 不再自动删除旧数据块"
    ),
    "Compression policy set: TimescaleDB compresses chunks older than {age} on its own schedule": (
        "压缩策略已设置：TimescaleDB 会按自己的计划压缩早于 {age} 的数据块"
    ),
    "Compression policy removed; TimescaleDB no longer compresses chunks automatically": (
        "压缩策略已删除；TimescaleDB 不再自动压缩数据块"
    ),
    "This hypertable has several retention policy jobs; manage them with SQL": (
        "此超表有多个保留策略任务；请使用 SQL 管理它们"
    ),
    "This hypertable has several compression policy jobs; manage them with SQL": (
        "此超表有多个压缩策略任务；请使用 SQL 管理它们"
    ),
    "The existing retention policy could not be read safely; manage it with SQL": (
        "无法安全地读取现有保留策略；请使用 SQL 管理它"
    ),
    "The existing compression policy could not be read safely; manage it with SQL": (
        "无法安全地读取现有压缩策略；请使用 SQL 管理它"
    ),
    "TimescaleDB retention policy planning timed out": "规划 TimescaleDB 保留策略超时",
    "TimescaleDB compression policy planning timed out": "规划 TimescaleDB 压缩策略超时",
    "TimescaleDB retention policy metadata could not be inspected safely": (
        "无法安全地查看 TimescaleDB 保留策略元数据"
    ),
    "TimescaleDB compression policy metadata could not be inspected safely": (
        "无法安全地查看 TimescaleDB 压缩策略元数据"
    ),
    "Enable compression on this hypertable first": "请先在此超表上启用压缩",
    "This hypertable has no retention policy": "此超表没有保留策略",
    "This hypertable has no compression policy": "此超表没有压缩策略",
    "Date dimensions require whole days, weeks, months or years": (
        "date 维度要求整数天、整数周、整数月或整数年"
    ),
    "The existing retention policy is paused; remove it before setting a new one": (
        "现有保留策略已暂停；请先删除它，再设置新策略"
    ),
    "The existing compression policy is paused; remove it before setting a new one": (
        "现有压缩策略已暂停；请先删除它，再设置新策略"
    ),
    # 连续聚合的刷新策略。
    "Set refresh policy": "设置刷新策略",
    "Remove refresh policy": "删除刷新策略",
    "Window starts": "窗口起点",
    "How long ago the refreshed window begins": "刷新的窗口从多久以前开始",
    "Window ends": "窗口终点",
    "How long ago it ends; more recent than the start": "窗口在多久以前结束；须比起点更接近当前",
    "Refresh every": "刷新间隔",
    "Set the refresh policy for {target}": "为 {target} 设置刷新策略",
    "Remove the refresh policy from {target}": "删除 {target} 的刷新策略",
    "Source hypertable: {source}": "源超表：{source}",
    "No refresh policy exists yet": "尚无刷新策略",
    "from the earliest data to the latest data": "从最早的数据到最新的数据",
    "from the earliest data to {end} ago": "从最早的数据到 {end} 以前",
    "from {start} ago to the latest data": "从 {start} 以前到最新的数据",
    "from {start} ago to {end} ago": "从 {start} 以前到 {end} 以前",
    "Removes job {job}, which refreshes {window} every {every}": (
        "删除任务 {job}，该任务每 {every} 刷新 {window}"
    ),
    "Replaces job {job}, which refreshes {window} every {every}": (
        "替换任务 {job}，该任务每 {every} 刷新 {window}"
    ),
    "New policy: refresh from {start} ago to {end} ago, every {every}": (
        "新策略：刷新 {start} 以前到 {end} 以前的数据，每 {every} 一次"
    ),
    "The source hypertable has no retention policy": "源超表没有保留策略",
    "The source drops chunks older than {age}; the window starts after that": (
        "数据源会删除早于 {age} 的数据块；窗口在该时限之后开始"
    ),
    "The source drops chunks {chunks}; check that it keeps the raw data this window refreshes": (
        "数据源会删除数据块 {chunks}；请确认它保留了此窗口所刷新的原始数据"
    ),
    "TimescaleDB stops refreshing this aggregate automatically; its materialized rows stay as they are": (
        "TimescaleDB 将停止自动刷新此聚合；其物化行保持原样"
    ),
    "TimescaleDB keeps refreshing this window on its own schedule, after this session ends": (
        "此会话结束后，TimescaleDB 仍会按自己的计划刷新此窗口"
    ),
    "This continuous aggregate has no refresh policy": "此连续聚合没有刷新策略",
    "Review the refresh policy plan before applying it": "应用前请查看刷新策略计划",
    "Refresh policy set: TimescaleDB refreshes this aggregate on its own schedule": (
        "刷新策略已设置：TimescaleDB 会按自己的计划刷新此聚合"
    ),
    "Refresh policy removed; TimescaleDB no longer refreshes this aggregate automatically": (
        "刷新策略已删除；TimescaleDB 不再自动刷新此聚合"
    ),
    "The existing refresh policy is paused; remove it before setting a new one": (
        "现有刷新策略已暂停；请先删除它，再设置新策略"
    ),
    "TimescaleDB refresh policy planning timed out": "规划 TimescaleDB 刷新策略超时",
    "TimescaleDB refresh policy metadata could not be inspected safely": (
        "无法安全地查看 TimescaleDB 刷新策略元数据"
    ),
    "This continuous aggregate has several refresh policy jobs; manage them with SQL": (
        "此连续聚合有多个刷新策略任务；请使用 SQL 管理它们"
    ),
    "The existing refresh policy could not be read safely; manage it with SQL": (
        "无法安全地读取现有刷新策略；请使用 SQL 管理它"
    ),
    "Date dimensions require offsets in whole days, weeks, months or years": (
        "date 维度的偏移量要求为整数天、整数周、整数月或整数年"
    ),
    "The window must start further back than it ends": "窗口起点必须比终点更早",
    "The window reaches data the source's retention policy drops (older than {age}); refreshing there would remove aggregated rows": (
        "窗口涉及数据源保留策略会删除的数据（早于 {age}）；在此处刷新会删除聚合行"
    ),
    # 压缩设置。
    "Configure compression": "配置压缩",
    "Segment by": "分段依据",
    "One column per line; leave empty for none": "每行一列；留空表示不设置",
    "Order by": "排序依据",
    "One column per line, optionally followed by ASC or DESC and NULLS FIRST or NULLS LAST; the time column is added descending when neither list names it": (
        "每行一列，可在后面加上 ASC 或 DESC 以及 NULLS FIRST 或 NULLS LAST；如果两个列表都未指定时间列，则会以降序加入时间列"
    ),
    "TimescaleDB compression settings could not be inspected safely": (
        "无法安全地查看 TimescaleDB 压缩设置"
    ),
    "Change the compression settings of {target}": "更改 {target} 的压缩设置",
    "Enable compression on {target}": "在 {target} 上启用压缩",
    "Current segment by: {columns}": "当前分段依据：{columns}",
    "Current segment by: none": "当前分段依据：无",
    "Current order by: {columns}": "当前排序依据：{columns}",
    "Current order by: none": "当前排序依据：无",
    "Compression is not enabled yet": "尚未启用压缩",
    "New segment by: {columns}": "新的分段依据：{columns}",
    "New segment by: none": "新的分段依据：无",
    "New order by: {columns}": "新的排序依据：{columns}",
    "Already compressed chunks keep the settings they were compressed with": (
        "已压缩的数据块会保留压缩时使用的设置"
    ),
    "TimescaleDB recommends segmenting or ordering by the unique column {column}": (
        "TimescaleDB 建议按唯一列 {column} 分段或排序"
    ),
    "Review the compression settings plan before applying it": (
        "应用前请查看压缩设置计划"
    ),
    "Compression settings changed; only chunks compressed from now on use them": (
        "压缩设置已更改；只有此后压缩的数据块会使用这些设置"
    ),
    "Compression enabled; chunks are compressed by a compression policy or on request": (
        "已启用压缩；数据块将由压缩策略或按请求进行压缩"
    ),
    "Nothing is compressed now; chunks are compressed later by a compression policy or on request": (
        "当前未压缩任何数据；数据块稍后由压缩策略或按请求压缩"
    ),
    "Only chunks compressed from now on use these settings; already compressed chunks keep theirs": (
        "只有此后压缩的数据块会使用这些设置；已压缩的数据块保留原有设置"
    ),
    "Locks this hypertable exclusively while the settings change; its reads and writes wait until it commits": (
        "更改设置期间会独占锁定此超表；其读写操作会等待提交"
    ),
    "Column \"{column}\" is listed more than once": "列“{column}”被列出了不止一次",
    "List at most {count} segment-by columns": "最多列出 {count} 个分段列",
    "List at most {count} order-by columns": "最多列出 {count} 个排序列",
    "Each line names one column": "每行只能指定一列",
    "This hypertable has no column \"{column}\"": "此超表没有列“{column}”",
    "The current compression settings could not be read": "无法读取当前压缩设置",
    "TimescaleDB compression settings planning timed out": "规划 TimescaleDB 压缩设置超时",
    # 转换表。
    "Convert to hypertable": "转换为超表",
    "The table becomes a hypertable, which DataPlayer cannot turn back into an ordinary table. Convert it?": (
        "该表将变为超表，DataPlayer 无法再将其改回普通表。要转换吗？"
    ),
    "Time column": "时间列",
    "A timestamp or date column of this table": "此表中类型为 timestamp 或 date 的列",
    "Chunk interval": "数据块间隔",
    "The table could not be inspected safely for conversion": (
        "无法安全地检查该表以进行转换"
    ),
    "Convert {target} into a hypertable": "将 {target} 转换为超表",
    "Time column: {column} ({type})": "时间列：{column}（{type}）",
    "Chunk interval: {interval}": "数据块间隔：{interval}",
    "The table is empty, and the conversion refuses if a row arrives before it runs": (
        "该表为空；如果在转换执行前有行写入，转换将被拒绝"
    ),
    "{column} becomes NOT NULL": "{column} 将变为 NOT NULL",
    "{column} becomes NOT NULL; a row without a time makes the conversion fail and roll back": (
        "{column} 将变为 NOT NULL；不含时间的行会导致转换失败并回滚"
    ),
    "An index on {column} alone already exists, so TimescaleDB adds none": (
        "已存在仅针对 {column} 的索引，因此 TimescaleDB 不会再添加"
    ),
    "TimescaleDB adds an index on {column}, newest first": (
        "TimescaleDB 会添加针对 {column} 的索引，最新的在前"
    ),
    "The table keeps its name and identity and becomes a hypertable; DataPlayer cannot turn it back into an ordinary table": (
        "该表保留其名称和身份并变为超表；DataPlayer 无法再将其改回普通表"
    ),
    "Locks this table exclusively for the conversion; its reads and writes wait until it commits": (
        "转换期间会独占锁定此表；其读写操作会等待提交"
    ),
    "Review the conversion plan before applying it": "应用前请查看转换计划",
    "Converted to a hypertable; rows added from now on are stored in chunks": (
        "已转换为超表；此后添加的行将存储在数据块中"
    ),
    "Choose an existing ordinary table": "请选择一个现有普通表",
    "This table is already a hypertable": "此表已经是超表",
    "Foreign keys between this table and a hypertable are not supported": (
        "不支持此表与超表之间的外键"
    ),
    "This table has no timestamp or date column to partition by": (
        "此表没有可用于分区的 timestamp 或 date 列"
    ),
    "This table has no timestamp, date or integer column to partition by": (
        "此表没有可用于分区的 timestamp、date 或整数列"
    ),
    "This table is not empty; only empty tables are converted here": (
        "此表不为空；此处只能转换空表"
    ),
    "This table has too many indexes to inspect": "此表的索引过多，无法检查",
    "The TimescaleDB conversion API is split across schemas": "TimescaleDB 转换 API 分散在多个模式中",
    "TimescaleDB conversion planning timed out": "规划 TimescaleDB 转换超时",
    "Only the table's owner can convert it": "只有表的所有者才能转换该表",
    "This connection may not read the table": "此连接无权读取该表",
    "Partitioned tables cannot become hypertables": "分区表不能变为超表",
    "Choose an ordinary table": "请选择普通表",
    "Tables with NO INHERIT constraints cannot become hypertables": (
        "带有 NO INHERIT 约束的表不能变为超表"
    ),
    "Tables that use inheritance cannot become hypertables": (
        "使用继承的表不能变为超表"
    ),
    "Only logged tables can become hypertables": "只有记录日志的表才能变为超表",
    "Tables with rules cannot become hypertables": "带有规则的表不能变为超表",
    "Choose a column this table can be partitioned by: {choices}": (
        "请选择可用于此表分区的列：{choices}"
    ),
    "Unique index \"{index}\" must include \"{column}\", which partitions the table": (
        "唯一索引“{index}”必须包含用于分区的列“{column}”"
    ),
    "An integer or UUID column is converted from Hypertable settings": (
        "整数或 UUID 列通过“超表设置”进行转换"
    ),
    "Date columns require whole days or weeks": "date 列要求整数天或整数周",
    # 压缩与解压数据块。
    "Compress chunks": "压缩数据块",
    "Decompress chunks": "解压数据块",
    "TimescaleDB chunk metadata could not be inspected safely": (
        "无法安全地查看 TimescaleDB 数据块元数据"
    ),
    "TimescaleDB chunk metadata could not be read": "无法读取 TimescaleDB 数据块元数据",
    "TimescaleDB chunk planning timed out": "规划 TimescaleDB 数据块操作超时",
    "Compress 1 chunk of {target} as a job": "以任务方式压缩 {target} 的 1 个数据块",
    "Compress {count} chunks of {target} as a job": "以任务方式压缩 {target} 的 {count} 个数据块",
    "Decompress 1 chunk of {target} as a job": "以任务方式解压 {target} 的 1 个数据块",
    "Decompress {count} chunks of {target} as a job": "以任务方式解压 {target} 的 {count} 个数据块",
    "Already compressed and left as they are: {count}": "已压缩并保持原样：{count}",
    "Already decompressed and left as they are: {count}": "已解压并保持原样：{count}",
    "Compressed chunks stay readable; queries and writes touching a chunk may wait while it is rewritten": (
        "压缩后的数据块仍可读取；在重写某个数据块期间，涉及该数据块的查询和写入可能需要等待"
    ),
    "Decompressed chunks take more space; a compression policy may compress them again on its own schedule": (
        "解压后的数据块占用更多空间；压缩策略可能会按自己的计划再次压缩它们"
    ),
    "Each chunk is converted in its own transaction; cancelling keeps the chunks already converted": (
        "每个数据块在各自的事务中转换；取消操作会保留已转换的数据块"
    ),
    "The hypertable could not be found; nothing was converted": "找不到超表；未转换任何内容",
    "Every whole chunk inside this window is already compressed": "此窗口内的所有完整数据块均已压缩",
    "No whole chunk inside this window is compressed": "此窗口内没有已压缩的完整数据块",
    "No whole chunk lies inside this window": "此窗口内没有完整的数据块",
    "More than {count} chunks lie inside this window; narrow it": (
        "此窗口内有超过 {count} 个数据块；请缩小窗口"
    ),
    "This chunk is in use; nothing was converted": "此数据块正在使用中；未转换任何内容",
    "The source cancelled converting this chunk after its fifteen minutes; it was rolled back": (
        "数据源在此数据块转换十五分钟后取消了转换；更改已回滚"
    ),
    "This connection may not convert this chunk": "此连接无权转换此数据块",
    "The connection was lost while this chunk was being converted; its outcome is unknown": (
        "转换此数据块时连接丢失；结果未知"
    ),
    "The source could not be reached; nothing was converted": "无法连接数据源；未转换任何内容",
    "The hypertable could not be checked in time; nothing was converted": (
        "未能及时检查超表；未转换任何内容"
    ),
    "The hypertable could not be checked safely; nothing was converted": (
        "无法安全地检查超表；未转换任何内容"
    ),
    "The hypertable or its TimescaleDB API changed after review; nothing was converted": (
        "查看后超表或其 TimescaleDB API 已更改；未转换任何内容"
    ),
    "This chunk is no longer part of the hypertable": "此数据块已不再属于该超表",
    "The source could not be reached or prepared; nothing was converted": (
        "无法连接或准备数据源；未转换任何内容"
    ),
    "The source refused to convert this chunk": "数据源拒绝转换此数据块",
    # 数据块维护。
    "Drop chunks": "删除数据块",
    "Drop these chunks and every row in them? This cannot be undone.": (
        "要删除这些数据块及其中的所有行吗？此操作无法撤销。"
    ),
    "Detach chunks": "分离数据块",
    "Merge chunks": "合并数据块",
    "Merge chunks, reads going on": "合并数据块（不影响读取）",
    "Move chunks to a tablespace": "将数据块移至表空间",
    "Reorder chunks by an index": "按索引重排数据块",
    "Split a chunk": "拆分数据块",
    "Attach a table as a chunk": "将表附加为数据块",
    "Drop chunks…": "删除数据块……",
    "Move chunks to a tablespace…": "将数据块移至表空间……",
    "Reorder chunks by an index…": "按索引重排数据块……",
    "Detach chunks…": "分离数据块……",
    "Merge chunks…": "合并数据块……",
    "Merge chunks, reads going on…": "合并数据块（不影响读取）……",
    "Tablespace": "表空间",
    "An existing tablespace this connection may create in": (
        "此连接可在其中创建的现有表空间"
    ),
    "Order rows by index": "按索引排列行",
    "Leave empty for the index on the time column": "留空表示使用时间列上的索引",
    "Index tablespace": "索引表空间",
    "Leave empty to move the indexes with the chunk": "留空表示将索引随数据块一起移动",
    "Index": "索引",
    "An index of this hypertable to order rows by": "用于排列此超表各行的索引",
    "Split at": "拆分点",
    "With its time zone; the chunk holding this instant is split at it": (
        "需带时区；包含该时间点的数据块将在此拆分"
    ),
    "Schema of the table": "表的模式",
    "Table": "表",
    "A table with the hypertable's columns, such as a detached chunk": (
        "具有超表各列的表，例如已分离的数据块"
    ),
    "Covering from": "覆盖起点",
    "Until": "终点",
    "Either a window or picked chunks, not both": "请选择窗口或挑选数据块，二者只能选其一",
    "Give where the window ends": "请给出窗口的终点",
    "With the chunk": "随数据块一起",
    "The index on the time column": "时间列上的索引",
    "A value of \"{column}\", the {type} column the hypertable is partitioned by": (
        "“{column}”的一个值，即超表用于分区的 {type} 列"
    ),
    "A value of \"{column}\", the {type} column the hypertable is partitioned by; leave empty for every earlier chunk": (
        "“{column}”的一个值，即超表用于分区的 {type} 列；留空表示所有更早的数据块"
    ),
    "A value of \"{column}\", the {type} column the hypertable is partitioned by; the chunk holding it is split at it": (
        "“{column}”的一个值，即超表用于分区的 {type} 列；包含该值的数据块将在此拆分"
    ),
    "Drop 1 chunk of {target} as a job": "以任务方式删除 {target} 的 1 个数据块",
    "Drop {count} chunks of {target} as a job": "以任务方式删除 {target} 的 {count} 个数据块",
    "Move 1 chunk of {target} as a job": "以任务方式移动 {target} 的 1 个数据块",
    "Move {count} chunks of {target} as a job": "以任务方式移动 {target} 的 {count} 个数据块",
    "Reorder 1 chunk of {target} as a job": "以任务方式重排 {target} 的 1 个数据块",
    "Reorder {count} chunks of {target} as a job": "以任务方式重排 {target} 的 {count} 个数据块",
    "Detach 1 chunk of {target} as a job": "以任务方式分离 {target} 的 1 个数据块",
    "Detach {count} chunks of {target} as a job": "以任务方式分离 {target} 的 {count} 个数据块",
    "Merge {count} chunks of {target} into one as a job": "以任务方式将 {target} 的 {count} 个数据块合并为一个",
    "Split {chunk} at {point} as a job": "以任务方式在 {point} 拆分 {chunk}",
    "Attach {table} to {target} as a chunk as a job": "以任务方式将 {table} 作为数据块附加到 {target}",
    "Exactly the chunks picked in the Chunks report, each read again by name": (
        "正是“数据块”报告中所挑选的数据块，每个都会按名称重新读取"
    ),
    "Left as they are, already in {tablespace}: {count}": "保持原样，已在 {tablespace} 中：{count}",
    "Left as they are, compressed, which reorder_chunk does not rewrite: {count}": (
        "保持原样，已压缩，reorder_chunk 不会重写：{count}"
    ),
    "Left as they are, compressed; TimescaleDB detaches only uncompressed chunks: {count}": (
        "保持原样，已压缩；TimescaleDB 只会分离未压缩的数据块：{count}"
    ),
    "Left as they are: {count}": "保持原样：{count}",
    "Every row in these chunks is deleted; each chunk is dropped by name, never by an age read when the job runs": (
        "这些数据块中的所有行都会被删除；每个数据块按名称删除，绝不会在任务运行时按读取到的时限删除"
    ),
    "Each chunk becomes an ordinary table under its own name and leaves the hypertable's queries; Detached chunks lists it, and Attach chunk brings it back": (
        "每个数据块都会以自己的名称成为普通表，并退出超表的查询；“已分离数据块”会列出它，“附加数据块”可将其收回"
    ),
    "The chunks become one, covering their whole range; the table is locked while they merge": (
        "这些数据块会合并为一个，覆盖它们的整个范围；合并期间表会被锁定"
    ),
    "The chunks become one, covering their whole range; reads go on meanwhile, writes to them wait": (
        "这些数据块会合并为一个，覆盖它们的整个范围；此期间读取照常进行，写入则需等待"
    ),
    "Each chunk is copied to the tablespace and the old copy removed; reads and writes to it wait meanwhile": (
        "每个数据块都会被复制到表空间并删除旧副本；此期间对它的读写会等待"
    ),
    "Each chunk is rewritten in the index's order, which speeds reads along it; reads and writes wait meanwhile": (
        "每个数据块都会按索引顺序重写，从而加快沿该索引的读取；此期间读写会等待"
    ),
    "The chunk becomes two, divided at this point; the table is locked while it splits": (
        "该数据块将在此点一分为二；拆分期间表会被锁定"
    ),
    "Its rows join the hypertable's queries; TimescaleDB refuses a table whose columns or rows do not fit": (
        "其行将加入超表的查询；如果表的列或行不匹配，TimescaleDB 会拒绝"
    ),
    "The hypertable could not be found; nothing was changed": "找不到超表；未更改任何内容",
    "This hypertable is partitioned by the integer column \"{column}\"; give its values, not instants": (
        "此超表按整数列“{column}”分区；请给出其值，而不是时间点"
    ),
    "This hypertable is partitioned by time on \"{column}\"; give instants, not numbers": (
        "此超表按“{column}”上的时间分区；请给出时间点，而不是数字"
    ),
    "Chunks of a hypertable partitioned by hash on {columns} are not merged here: which partition a chunk is in is not public, so the result could not be checked first": (
        "此处不合并按 {columns} 哈希分区的超表数据块：数据块所属的分区并非公开信息，因此无法先检查结果"
    ),
    "Chunks of a hypertable partitioned by hash on {columns} are not attached here: which partition a chunk is in is not public, so the result could not be checked first": (
        "此处不附加按 {columns} 哈希分区的超表数据块：数据块所属的分区并非公开信息，因此无法先检查结果"
    ),
    "TimescaleDB splits no chunk of a hypertable partitioned by hash as well as by time": (
        "TimescaleDB 不会拆分同时按哈希和时间分区的超表数据块"
    ),
    "Pick at least one chunk": "请至少选择一个数据块",
    "Pick at most {count} chunks at a time": "每次最多选择 {count} 个数据块",
    "\"{name}\" is not a chunk of this hypertable any more": "“{name}”已不再是此超表的数据块",
    "Tablespace \"{name}\" does not exist or this connection may not create in it": (
        "表空间“{name}”不存在，或此连接无权在其中创建"
    ),
    "This hypertable has no index \"{index}\"": "此超表没有索引“{index}”",
    "Every whole chunk inside this window is already in {tablespace}": "此窗口内的所有完整数据块都已在 {tablespace} 中",
    "Every picked chunk is already in {tablespace}": "所有挑选的数据块都已在 {tablespace} 中",
    "Every whole chunk inside this window is compressed, which reorder_chunk does not rewrite": (
        "此窗口内的所有完整数据块均已压缩，reorder_chunk 不会重写它们"
    ),
    "Every picked chunk is compressed, which reorder_chunk does not rewrite": (
        "所有挑选的数据块均已压缩，reorder_chunk 不会重写它们"
    ),
    "Every whole chunk inside this window is compressed; TimescaleDB detaches only uncompressed chunks": (
        "此窗口内的所有完整数据块均已压缩；TimescaleDB 只会分离未压缩的数据块"
    ),
    "Every picked chunk is compressed; TimescaleDB detaches only uncompressed chunks": (
        "所有挑选的数据块均已压缩；TimescaleDB 只会分离未压缩的数据块"
    ),
    "Name an index: moving a chunk rewrites it in an index's order": (
        "请指定索引：移动数据块会按索引顺序重写它"
    ),
    "A merge needs at least two chunks": "合并至少需要两个数据块",
    "Chunks \"{before}\" and \"{after}\" are not adjacent; choose chunks that touch": (
        "数据块“{before}”和“{after}”不相邻；请选择彼此相接的数据块"
    ),
    "TimescaleDB {version} cannot merge compressed chunks; decompress them first": (
        "TimescaleDB {version} 无法合并已压缩的数据块；请先解压它们"
    ),
    "No chunk holds this point strictly inside its range": "没有数据块将该点严格包含在其范围内",
    "There is no table \"{schema}\".\"{table}\"": "不存在表“{schema}”.“{table}”",
    "Only an ordinary table can become a chunk": "只有普通表才能成为数据块",
    "Only the table's owner can attach it": "只有表的所有者才能附加该表",
    "A hypertable cannot become a chunk": "超表不能成为数据块",
    "This table is already a chunk": "此表已经是数据块",
    "A table that uses inheritance cannot become a chunk": "使用继承的表不能成为数据块",
    "Chunk \"{name}\" already covers part of this range": "数据块“{name}”已覆盖此范围的一部分",
    "The range is empty once read in the column's type": "按列类型读取后该范围为空",
    "This chunk is in use; nothing was changed": "此数据块正在使用中；未更改任何内容",
    "The source cancelled this unit after its fifteen minutes; it was rolled back": (
        "数据源在此单元运行十五分钟后取消了操作；更改已回滚"
    ),
    "This connection may not change this chunk": "此连接无权更改此数据块",
    "The connection was lost while this unit was running; its outcome is unknown": (
        "此单元运行时连接丢失；结果未知"
    ),
    "The hypertable could not be checked in time; nothing was changed": (
        "未能及时检查超表；未更改任何内容"
    ),
    "The hypertable or its chunks changed after review; nothing was changed": (
        "查看后超表或其数据块已更改；未更改任何内容"
    ),
    "The hypertable could not be checked safely; nothing was changed": (
        "无法安全地检查超表；未更改任何内容"
    ),
    "The source could not be reached; nothing was changed": "无法连接数据源；未更改任何内容",
    "The table to attach is gone; nothing was changed": "要附加的表已不存在；未更改任何内容",
    "This chunk was compressed after review; it was left as it is": (
        "查看后此数据块已被压缩；已保持原样"
    ),
    "These chunks changed after review; nothing was merged": "查看后这些数据块已更改；未合并任何内容",
    "The index to order rows by is gone; nothing was changed": (
        "用于排列行的索引已不存在；未更改任何内容"
    ),
    "The source could not be reached or prepared; nothing was changed": (
        "无法连接或准备数据源；未更改任何内容"
    ),
    "The source refused this unit; nothing was changed": "数据源拒绝了此单元；未更改任何内容",
    "This is not offered over these rows": "这些行不支持此操作",
    "A chunk is named by its schema and its name": "数据块由其模式和名称标识",
    "The picked chunks belong to {count} hypertables; pick chunks of one": (
        "挑选的数据块属于 {count} 个超表；请只选择一个超表的数据块"
    ),
    "Some picked rows are not chunks any more; read the report again": (
        "部分挑选的行已不再是数据块；请重新读取报告"
    ),
    # 按列跳过数据块。
    "Skip chunks by a column": "按列跳过数据块",
    "Stop skipping chunks by a column": "停止按列跳过数据块",
    "Column": "列",
    "An integer, date or timestamp column queries filter on": "查询会筛选的整数、date 或 timestamp 列",
    "The hypertable could not be inspected safely": "无法安全地查看超表",
    "TimescaleDB keeps ranges only of integer, date and timestamp columns, not of \"{column}\" ({type})": (
        "TimescaleDB 只记录整数、date 和 timestamp 列的范围，不记录“{column}”（{type}）的范围"
    ),
    "Planning chunk skipping timed out": "规划数据块跳过超时",
    "Chunks record the range of {column} as they are compressed, and a query filtering on it skips the chunks outside": (
        "数据块在压缩时会记录 {column} 的范围，按其筛选的查询会跳过范围之外的数据块"
    ),
    "Chunks stop recording the range of {column}, if they did": (
        "数据块将停止记录 {column} 的范围（如果此前记录）"
    ),
    "Changes nothing if it already holds: TimescaleDB keeps which columns record ranges where this application does not read": (
        "如果已经如此则不会产生任何更改：在本应用不读取的位置，TimescaleDB 仍会保留哪些列记录范围"
    ),
    "timescaledb.enable_chunk_skipping is off for this connection; queries use the ranges only in sessions that turn it on": (
        "此连接已关闭 timescaledb.enable_chunk_skipping；查询仅在开启该设置的会话中使用这些范围"
    ),
    "Skip chunks by {column} on {target}": "在 {target} 上按 {column} 跳过数据块",
    "Stop skipping chunks by {column} on {target}": "在 {target} 上停止按 {column} 跳过数据块",
    "Review the chunk skipping plan before applying it": "应用前请查看数据块跳过计划",
    "Chunk skipping turned on": "数据块跳过已开启",
    "Chunk skipping turned off": "数据块跳过已关闭",
    # 超表设置：读取超表。
    "Hypertable settings": "超表设置",
    "Reading the hypertable timed out": "读取超表超时",
    "Job {job} drops chunks {chunks}, every {every}": "任务 {job} 每 {every} 删除数据块 {chunks}",
    "Job {job} drops chunks {chunks}, every {every}; paused": (
        "任务 {job} 每 {every} 删除数据块 {chunks}；已暂停"
    ),
    "Job {job} compresses chunks {chunks}, every {every}": "任务 {job} 每 {every} 压缩数据块 {chunks}",
    "Job {job} compresses chunks {chunks}, every {every}; paused": (
        "任务 {job} 每 {every} 压缩数据块 {chunks}；已暂停"
    ),
    "Job {job} reorders chunks by {index}": "任务 {job} 按 {index} 重排数据块",
    "Job {job} reorders chunks by {index}; paused": "任务 {job} 按 {index} 重排数据块；已暂停",
    "Job {job} reorders chunks by an index this editor cannot read": (
        "任务 {job} 按此编辑器无法读取的索引重排数据块"
    ),
    "Job {job} reorders chunks by an index this editor cannot read; paused": (
        "任务 {job} 按此编辑器无法读取的索引重排数据块；已暂停"
    ),
    "The current sparse indexes could not be read": "无法读取当前稀疏索引",
    "This hypertable has a sparse index of a kind this editor does not know; manage it with SQL": (
        "此超表有一个此编辑器不认识的稀疏索引；请使用 SQL 管理它"
    ),
    "The current columnstore settings could not be read": (
        "无法读取当前列式存储设置"
    ),
    "This hypertable merges compressed chunks by a time interval; manage it with SQL": (
        "此超表按时间间隔合并已压缩的数据块；请使用 SQL 管理"
    ),
    "This hypertable has several compaction policy jobs; manage them with SQL": (
        "此超表有多个压实策略任务；请使用 SQL 管理它们"
    ),
    "This hypertable has several reorder policy jobs; manage them with SQL": (
        "此超表有多个重排策略任务；请使用 SQL 管理它们"
    ),
    "The existing reorder policy could not be read safely; manage it with SQL": (
        "无法安全地读取现有重排策略；请使用 SQL 管理它"
    ),
    "TimescaleDB {version} partitions by UUIDv7 only partly; it is edited here from 2.25": (
        "TimescaleDB {version} 仅部分支持按 UUIDv7 分区；从 2.25 起可在此编辑"
    ),
    "Only timestamp, date, UUIDv7 and integer time dimensions are edited here": (
        "此处仅编辑 timestamp、date、UUIDv7 和整数时间维度"
    ),
    "The current chunk interval could not be read": "无法读取当前数据块间隔",
    "Only hash dimensions beside the time dimension are edited here": (
        "此处仅编辑时间维度旁的哈希维度"
    ),
    "The hypertable's chunks and tablespaces could not be read": (
        "无法读取超表的数据块和表空间"
    ),
    "This connection may not create functions in schema \"{schema}\"": (
        "此连接无权在模式“{schema}”中创建函数"
    ),
    "A function named \"{name}\" already exists; choose it from the list or another name": (
        "已存在名为“{name}”的函数；请从列表中选择它，或选择其他名称"
    ),
    "A chunk interval of an integer column is a number of its values": "整数列的数据块间隔是其值的个数",
    "A chunk interval of a {type} column is at most {count}": "{type} 列的数据块间隔最大为 {count}",
    "A chunk interval is counted in minutes, hours, days or weeks": (
        "数据块间隔以分钟、小时、天或周计"
    ),
    # 超表设置：规划更改。
    "Locks this hypertable exclusively while it changes; its reads and writes wait until it commits": (
        "更改期间会独占锁定此超表；其读写操作会等待提交"
    ),
    "Other changes to this hypertable's settings wait until it commits": (
        "对此超表设置的其他更改会等待提交"
    ),
    "A chunk interval of this hypertable is counted in days or weeks": (
        "此超表的数据块间隔以天或周计"
    ),
    "A chunk interval of this hypertable is counted in minutes or hours or days or weeks": (
        "此超表的数据块间隔以分钟、小时、天或周计"
    ),
    "A chunk interval of this column is counted in days or weeks": (
        "此列的数据块间隔以天或周计"
    ),
    "A chunk interval of this column is counted in minutes or hours or days or weeks": (
        "此列的数据块间隔以分钟、小时、天或周计"
    ),
    "Column \"{column}\" has a type that cannot be used as a hash dimension": (
        "列“{column}”的类型不能用作哈希维度"
    ),
    "Column \"{column}\" has a type that cannot be used as a minmax sparse index": (
        "列“{column}”的类型不能用作 minmax 稀疏索引"
    ),
    "Column \"{column}\" has a type that cannot be used as a segment column": (
        "列“{column}”的类型不能用作分段列"
    ),
    "Column \"{column}\" has a type that cannot be used as an order column": (
        "列“{column}”的类型不能用作排序列"
    ),
    "TimescaleDB cannot remove the hash dimension on \"{column}\"": (
        "TimescaleDB 无法移除“{column}”上的哈希维度"
    ),
    "A hash dimension can only be added while the hypertable holds no chunks": (
        "只有在超表不包含任何数据块时才能添加哈希维度"
    ),
    "The time column cannot also be a hash dimension": "时间列不能同时作为哈希维度",
    "Unique key \"{key}\" must include \"{column}\" before it can be a hash dimension": (
        "唯一键“{key}”必须包含“{column}”才能作为哈希维度"
    ),
    "TimescaleDB {version} has no sparse indexes; they arrived in 2.22": (
        "TimescaleDB {version} 没有稀疏索引；该功能自 2.22 起提供"
    ),
    "Column \"{column}\" has the same sparse index twice": "列“{column}”重复包含同一个稀疏索引",
    "Sparse indexes need the order to be named; choose the columns to order by": (
        "稀疏索引需要指定顺序；请选择排序列"
    ),
    "Column \"{column}\" is listed more than once in the columnstore settings": (
        "列“{column}”在列式存储设置中被列出了不止一次"
    ),
    "The columnstore cannot be turned off while chunks are compressed; decompress them first": (
        "存在压缩数据块时无法关闭列式存储；请先解压它们"
    ),
    "TimescaleDB {version} cannot return a setting to its own choice; name the columns instead": (
        "TimescaleDB {version} 无法将设置恢复为自动选择；请改为指定列"
    ),
    "Merging compressed chunks is set in time, which an integer column does not count in": (
        "合并已压缩数据块的设置以时间表示，而整数列不按时间计数"
    ),
    "A merge interval is counted in the units of the chunk interval": (
        "合并间隔以数据块间隔的单位计"
    ),
    "The merge interval must be a whole multiple of the chunk interval, larger than it": (
        "合并间隔必须是数据块间隔的整数倍，且大于数据块间隔"
    ),
    "There is no retention policy to keep": "没有可保留的保留策略",
    "There is no compression policy to keep": "没有可保留的压缩策略",
    "The retention policy of an integer column is a number of its values": (
        "整数列的保留策略是其值的个数"
    ),
    "The compression policy of an integer column is a number of its values": (
        "整数列的压缩策略是其值的个数"
    ),
    "The retention policy of a {type} column is at most {count}": "{type} 列的保留策略最大为 {count}",
    "The compression policy of a {type} column is at most {count}": "{type} 列的压缩策略最大为 {count}",
    "The retention policy of a {type} column cannot count in plain numbers": (
        "{type} 列的保留策略不能以普通数字计"
    ),
    "The compression policy of a {type} column cannot count in plain numbers": (
        "{type} 列的压缩策略不能以普通数字计"
    ),
    "The retention policy of a {type} column cannot count in seconds": (
        "{type} 列的保留策略不能以秒计"
    ),
    "The compression policy of a {type} column cannot count in seconds": (
        "{type} 列的压缩策略不能以秒计"
    ),
    "The retention policy of a {type} column cannot count in minutes": (
        "{type} 列的保留策略不能以分钟计"
    ),
    "The compression policy of a {type} column cannot count in minutes": (
        "{type} 列的压缩策略不能以分钟计"
    ),
    "The retention policy of a {type} column cannot count in hours": (
        "{type} 列的保留策略不能以小时计"
    ),
    "The compression policy of a {type} column cannot count in hours": (
        "{type} 列的压缩策略不能以小时计"
    ),
    "The existing reorder policy is paused; remove it before setting a new one": (
        "现有重排策略已暂停；请先删除它，再设置新策略"
    ),
    "Only a hypertable partitioned by an integer column takes an integer_now function": (
        "只有按整数列分区的超表才能使用 integer_now 函数"
    ),
    "TimescaleDB cannot take an integer_now function away; keep it or choose another": (
        "TimescaleDB 无法移除 integer_now 函数；请保留它或另选一个"
    ),
    "There is no integer_now function to keep": "没有可保留的 integer_now 函数",
    "{function} is not a function TimescaleDB accepts as integer_now of a {type} column": (
        "{function} 不是 TimescaleDB 可接受的、用于 {type} 列的 integer_now 函数"
    ),
    "A {type} column cannot hold the seconds since 1970": "{type} 列无法保存自 1970 年以来的秒数",
    "A {type} column cannot hold the milliseconds since 1970": (
        "{type} 列无法保存自 1970 年以来的毫秒数"
    ),
    "A {type} column cannot hold the microseconds since 1970": (
        "{type} 列无法保存自 1970 年以来的微秒数"
    ),
    "TimescaleDB {version} has no compaction policy; it arrived in 2.29": (
        "TimescaleDB {version} 没有压实策略；该功能自 2.29 起提供"
    ),
    "A compaction policy merges compressed chunks; turn the columnstore on": (
        "压实策略会合并已压缩的数据块；请开启列式存储"
    ),
    "Remove the columnstore policy to turn the columnstore off": (
        "要关闭列式存储，请删除列式存储策略"
    ),
    "Remove the compaction policy to turn the columnstore off": (
        "要关闭列式存储，请删除压实策略"
    ),
    "An age policy on an integer column needs an integer_now function to tell the current value": (
        "整数列上的时效策略需要 integer_now 函数来提供当前值"
    ),
    "Choose the time column the table is partitioned by": "请选择表用于分区的时间列",
    "Choose the chunk interval": "请选择数据块间隔",
    "TimescaleDB cannot change the time column of a hypertable": "TimescaleDB 无法更改超表的时间列",
    "Planning the hypertable change timed out": "规划超表更改超时",
    # 超表设置：预览。
    "TimescaleDB's choice for each chunk": "TimescaleDB 为每个数据块自动选择",
    "TimescaleDB's choice": "TimescaleDB 自动选择",
    "none": "无",
    "segment by {columns}": "按 {columns} 分段",
    "order by {columns}": "按 {columns} 排序",
    "sparse indexes {indexes}": "稀疏索引 {indexes}",
    "{kind} on {column}": "{column} 上的 {kind}",
    "no merging of chunks": "不合并数据块",
    "merge chunks into {length} as they are compressed": "在压缩时合并为 {length} 的数据块",
    "Turn the columnstore on: {changes}": "开启列式存储：{changes}",
    "Columnstore settings for chunks compressed from now on: {changes}": (
        "此后压缩的数据块的列式存储设置：{changes}"
    ),
    "Convert the table into a hypertable by {column} ({type}), chunks of {length}, and move its rows into chunks": (
        "按 {column}（{type}）将表转换为超表，数据块大小为 {length}，并将其行移入数据块"
    ),
    "Convert the table into a hypertable by {column} ({type}), chunks of {length}, while it is empty": (
        "在表为空时按 {column}（{type}）将其转换为超表，数据块大小为 {length}"
    ),
    "Remove the retention policy (job {job})": "删除保留策略（任务 {job}）",
    "Remove the columnstore policy (job {job})": "删除列式存储策略（任务 {job}）",
    "Remove the reorder policy (job {job})": "删除重排策略（任务 {job}）",
    "Remove the compaction policy (job {job})": "删除压实策略（任务 {job}）",
    "Add a retention policy: drop chunks older than {length}": (
        "添加保留策略：删除早于 {length} 的数据块"
    ),
    "Add a columnstore policy: compress chunks older than {length}": (
        "添加列式存储策略：压缩早于 {length} 的数据块"
    ),
    "Add a compaction policy: merge small compressed chunks on TimescaleDB's schedule": (
        "添加压实策略：按 TimescaleDB 的计划合并较小的已压缩数据块"
    ),
    "Add a reorder policy by index {index}": "添加按索引 {index} 的重排策略",
    "New chunks cover {length}; existing chunks keep their range": (
        "新数据块覆盖 {length}；现有数据块保留其范围"
    ),
    "Hash {column} into {partitions} partitions for new chunks": (
        "将 {column} 哈希到 {partitions} 个分区供新数据块使用"
    ),
    "Add a hash dimension on {column} with {partitions} partitions": (
        "在 {column} 上添加包含 {partitions} 个分区的哈希维度"
    ),
    "Turn the columnstore off": "关闭列式存储",
    "Place new chunks in tablespace {tablespace} too": "也将新数据块放入表空间 {tablespace}",
    "Stop placing new chunks in tablespace {tablespace}": (
        "不再将新数据块放入表空间 {tablespace}"
    ),
    "Create function {function} returning the seconds since 1970 as {type}": (
        "创建函数 {function}，以 {type} 返回自 1970 年以来的秒数"
    ),
    "Create function {function} returning the milliseconds since 1970 as {type}": (
        "创建函数 {function}，以 {type} 返回自 1970 年以来的毫秒数"
    ),
    "Create function {function} returning the microseconds since 1970 as {type}": (
        "创建函数 {function}，以 {type} 返回自 1970 年以来的微秒数"
    ),
    "Policies take the current value of the time column from {function}": (
        "策略从 {function} 获取时间列的当前值"
    ),
    "Moves about {count} rows into chunks as a job in Activity; the table is locked against reads and writes until it ends": (
        "在“活动”中作为任务将约 {count} 行移入数据块；任务结束前表将被锁定，无法读写"
    ),
    "Moves an unknown number of rows into chunks as a job in Activity; the table is locked against reads and writes until it ends": (
        "在“活动”中作为任务将未知数量的行移入数据块；任务结束前表将被锁定，无法读写"
    ),
    "Rolled back whole if it fails, is cancelled or runs past {seconds} seconds; nothing is left half converted": (
        "如果失败、被取消或超过 {seconds} 秒，将整体回滚；不会留下转换到一半的内容"
    ),
    "DataPlayer cannot turn a hypertable back into an ordinary table": (
        "DataPlayer 无法将超表改回普通表"
    ),
    "TimescaleDB keeps dropping whole chunks past the retention age on its own schedule, after this session ends": (
        "此会话结束后，TimescaleDB 仍会按自己的计划删除超过保留时限的完整数据块"
    ),
    "{target} already matches these settings": "{target} 已符合这些设置",
    "Change {target}": "更改 {target}",
    "Review the hypertable plan before applying it": "应用前请查看超表计划",
    "Moving rows into chunks runs as a job; start it from the plan": (
        "将行移入数据块会作为任务运行；请从计划中启动它"
    ),
    "Converted to a hypertable": "已转换为超表",
    "Hypertable changed: 1 change applied": "超表已更改：已应用 1 项更改",
    "Hypertable changed: {count} changes applied": "超表已更改：已应用 {count} 项更改",
    "This change is applied at once rather than as a job": "此更改会立即应用，而不是作为任务运行",
    "The table could not be found; nothing was converted": "找不到该表；未转换任何内容",
    "The table was renamed after review; nothing was converted": (
        "查看后表已被重命名；未转换任何内容"
    ),
    # 按超表设计的表。
    "Hypertable": "超表",
    "Columnstore": "列式存储",
    "Retention policy": "保留策略",
    "Columnstore policy": "列式存储策略",
    "Compaction policy": "压实策略",
    "Reorder policy": "重排策略",
    "Integer now": "Integer now",
    "Function {name}": "函数 {name}",
    "Hash dimension {column}": "哈希维度 {column}",
    "The segment list names a column that is not there": "分段列表指定了一个不存在的列",
    "The order list names a column that is not there": "排序列表指定了一个不存在的列",
    "The sparse index names a column that is not there": "稀疏索引指定了一个不存在的列",
    "The time dimension names a column that is not there": "时间维度指定了一个不存在的列",
    "The hash dimension names a column that is not there": "哈希维度指定了一个不存在的列",
    "Choose the columns to segment by": "请选择用于分段的列",
    "Choose the columns to order by": "请选择用于排序的列",
    "Choose the columns of the sparse indexes": "请选择稀疏索引的列",
    "The reorder policy names an index that is not there": "重排策略指定了一个不存在的索引",
    "The TimescaleDB API is split across schemas": "TimescaleDB API 分散在多个模式中",
    "This setting cannot be made while the table is created": "创建表时无法进行此设置",
    "\"{column}\" cannot partition a hypertable; choose a timestamp or date column": (
        "“{column}”无法对超表分区；请选择 timestamp 或 date 列"
    ),
    "\"{column}\" partitions the hypertable, so it must have a value": (
        "“{column}”用于超表分区，因此必须有值"
    ),
    "TimescaleDB {version} partitions by UUIDv7 only partly; choose a timestamp column": (
        "TimescaleDB {version} 仅部分支持按 UUIDv7 分区；请选择 timestamp 列"
    ),
}
