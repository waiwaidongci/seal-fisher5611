# 实际验证记录

本文件记录在当前环境中真实执行过的验证，而不是设计意图。环境：Linux arm64、Python 3.11.2、SQLite 作为测试库替身、Node 22 用于前端语法检查；未在本机启动 MySQL/Redis/Docker。

## 可运行单元与集成测试

```bash
cd backend
pip install -r requirements-dev.txt   # 生产依赖 + pytest/httpx
python -m pytest tests -q
```
测试自带 SQLite 库与假 Redis，无需启动 MySQL/Redis。

结果：**31 passed**（`tests/test_competing_risk.py` 20 项，`tests/test_api.py` 11 项）。

### tests/test_competing_risk.py（算法 oracle）
- `test_matches_direct_aalen_johansen`：4 组随机批次（各 120 件），在多个指定日与独立 O(n²) 逐项重算比对累计发生率与在险数，误差 <1e-12。
- `test_risk_difference_is_b_minus_a`：风险差确为 B−A。
- `test_break_is_competing_event_not_leak`：破包不计入漏封分子，且降低后续事件自由生存。
- `test_delayed_entry_joins_risk_set_before_same_day_event`：迟入组试件计入同刻事件分母（1/2 而非 1/1）。
- `test_same_instant_loss_does_not_shrink_event_denominator`：同刻失访在事件之后移除，分母保持 2。
- `test_leak_and_break_same_instant_are_counted_together`：同刻漏封与破包合并计入。
- `test_day_after_all_outcomes_is_refused` / `test_day_before_first_entry_is_refused` / `test_day_inside_an_unobserved_gap_is_refused`：无在险观察的指定日拒绝出结论，恢复观察后的指定日可正常计算。
- `test_day_inside_support_with_no_event_yet_is_answered`：指定日在支持内但尚无事件时给出 0。
- `test_incomplete_outcome_combination_is_rejected`、`test_outcome_before_entry_is_rejected`、`test_unknown_group_is_rejected`、`test_empty_group_is_refused`、`test_negative_and_non_finite_days_are_rejected`：非法输入明确拒绝。
- `test_overrun_deadline_refuses`：`deadline` 已过时返回拒绝原因（“时限”）。
- `test_hundred_thousand_specimens_finishes_within_five_seconds`：真实十万件批次在5秒内完成并给出风险差。

### tests/test_api.py（HTTP 链路）
- 旧试封研究默认 `seal_fisher`，原 Fisher 运行仍产出 `Fisher双侧p`、合格率等指标。
- 新 `shelf_risk` 运行产出 `B减A漏封风险差`、A/B 指定日在险件数、方法与假设明细。
- 指定日超出在险支持时，计算抛“拒绝出结论”；前端把它渲染为 failed 并显示原因。
- 参数按研究类型白名单：shelf 传 `alpha` 或 fisher 传 `day` 均 422。
- 整批更正原子性：一条无效则整批 422，库中两行保持原值。
- 按 row_id 整批更正可同时改 A 与 B 两边；批量新增沿用重复源记录编号拒绝（409）。
- 快照隔离：排队前的运行快照保持旧值，更正后新运行的快照与 checksum 变化。
- 非法的结局组合（早于入组、同时漏封+破包）拒绝；观察员不能写入。

## 其他实测
- 十万件规模：`calculate_competing_risk` 单次 0.16–0.29 秒（含解析、排序与两组成分），低于 5 秒；`deadline` 检查在解析与逐时点循环中执行。
- 批量插入 100,000 件 + 冻结运行快照：在 SQLite 上分别约 4.0 秒与 2.0 秒（单事务；这是数据库写入路径，不是 5 秒计算限的适用范围）。
- `scripts.seed_demo.py` 在 SQLite 上成功生成 3 个试封批次 + 1 个货架留样批次（180 件逐件记录），重复执行不覆盖已修改记录。
- 前端全部 ES module 通过 `node --check`。

## 未验证
- 未在本机启动 MySQL 8 / Redis 7 / Docker Compose，也未做浏览器端点击回归。
- 未在本机实测 worker 心跳与 artifacts 卷写入（worker 计算路径以同一 `compute()` 在测试中覆盖）。
