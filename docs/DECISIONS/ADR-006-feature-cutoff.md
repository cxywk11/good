# ADR-006: 系统可见性优先于事件时间

状态：接受。范围：P4-2；2026-10-01。

cutoff 必须是带时区时间，规范化 UTC，不接受未来时间；V1 只允许早于当时版本开球时间的赛前 cutoff。所有比较按 <= cutoff（赛后 finished_at 必须 < cutoff）。未知 published_at/effective_at 可为空，但系统时间证据不能缺失。

每个输入必须同时通过自身 collected_at/observed_at、created_at、非空 published_at/effective_at，以及关联 Raw 的同类约束。所有不可变输入还需 analysis_visibility.visible_at <= cutoff。可见性凭据由独立连接读到已提交记录后采样系统 UTC 时间，在单独事务只追加；不能使用源提供的时间或旧 created_at 生成早期凭据。

ORM 提交后记录凭据；Feature 重建前再完成一次凭据检查，唯一键解决并发，未提交或新补写的输入不能获得过去的凭据。记录失败有日志，输入保持不可用；Core 写入和迁移前数据只从首次实际确认时开始可用于 Feature。旧时期从未保留提交证据的事实不可推测，旧展示接口仍维持原语义。

比赛从 match_versions 和其 Raw 恢复；名称、球队 UUID、开球等不读可变当前值。映射从 cutoff 前已可见的 audit_logs 恢复，只允许匹配目标及版本的确认绑定；赔率变化不跨映射版本。观察的新鲜度也检查其 Raw 和凭据。

历史赛后事实还要验证绑定比赛版本可见、当时参与球队与开球没有冲突、finished_at < cutoff，排除目标比赛自身标签。修正只在新的观察和提交凭据时间之后可见。当前没有新闻/阵容 Evidence Provider，输出明确为空；未来接入须遵循同一规则。

保证依赖受信任的系统 UTC 时钟、正常应用写入口及不可变数据库权限。具有超级用户权限者禁用触发器/伪造凭据不在应用威胁模型内；生产需时间同步和受限角色。此次不改造旧赔率历史逻辑。
