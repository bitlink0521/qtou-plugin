# 固定源与生成入口

源：https://github.com/bitlink0521/qtou/tree/877e4ad9eb8f8435c30b55b12949268d0cb24e30

- AgentMcpService.java:91–94 tools/list → toolDefs()；489–552 基础定义；726起 createAlertSchema/tool/schema 辅助。
- 必须合并 AgentRiskMcpPostProcessor.java:73–90 的 tools/list 后处理，不能只抽取 toolDefs：追加 AgentRiskMcpTools.defs()，并对原 schema 作补丁；该文件125起、203起含 schema 修饰逻辑。
- AgentMcpService.java:547 使用 AgentUserFields.KEYS 和 AgentEntryFields.LABELS。
- AgentMcpService.java:550 使用 AgentBpMediaService.assetSchema()；551 使用 AgentBpService.evidenceSchema()。
- AgentBpService.evidenceSchema() 使用同文件静态 FIELDS、object/array/schemaTree/obj 等辅助；不要仅截157–167行丢掉静态字段与辅助实现。
- AgentRiskMcpTools.defs() 的 schema 在同文件构造，不需要调用其业务方法或注入业务服务。

本包为七份未改写原始Java源码与SHA256清单。`tools/generate_qtou_tool_catalog.py` 按上述组装顺序生成 `tools/qtou_tool_catalog.json`，并写入这些源文件的 SHA256。缺直接依赖、哈希不符或 schema 解析不完整时生成器退出，不写出残缺目录。
