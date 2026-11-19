# 砚田包装试封比较席

两种封口工艺独立合格/失败计数→固定方案比较→复试决策；双侧Fisher按概率不大于观测表求和。另设货架留样研究：按件补录迟入组与首次漏封、破包、失访，在指定日比较竞争风险累计发生率。原生 HTML/CSS/JavaScript 多模块工作席，所有计算由 Python 完成。

## 模拟业务
砚田研究协作组，12名分析师与业务人员，日常使用 `seal-fisher-202611-1.csv` 手工抄表。当前三个痛点：观测与口径不可追溯、重算易出错、结果与复核割裂。上游提供独立合成业务观测；本应用接管数据登记、方法执行和输入冻结；下游负责人形成复测/预算方案，观察员获取复核后的CSV。

核心业务实体：SealTrial / TrialCount / ExactRun / TrialDecision。源码 model/schema/service/controller/route 与前端 api/store/pages 完成链路，不依赖浏览器本地假数据。

## 功能与方法
- 两类研究批次：`seal_fisher`（试封计数比较，历史口径不变）与 `shelf_risk`（货架期竞争风险）。批次与运行都固定研究类型，参数按类型白名单校验。
- 试封方案、工艺计数录入/编辑/删除；重名记录与非法数值明确拒绝。
- Fisher精确检验、Wilson单比例区间与率差。两组试件独立，组别预先固定。双侧 p 值是固定边际下概率不大于观察表的所有表之和。
- 货架留样按件录入：上架后天数计的补录入组日，以及首次漏封/破包/失访之一（可留空表示仍在观察）。累计发生率用竞争风险 Aalen-Johansen：漏封为目标事件，破包为竞争事件，失访为非信息删失；风险集按迟入组左截断构造。
- 同一时刻的既定顺序：先加入迟入组试件，再把漏封与破包合并计入该时刻，最后移除失访；因此删失不会缩小同刻事件的在险分母。
- 指定日无任何在险观察时拒绝出结论，不把上一时点的值外推；十万件计算限5秒，超时同样拒绝。
- 整批更正：一次请求可同时更正A、B两边，单事务提交；并发排队只取更正前或更正后的完整输入。计算期间补录照常，且只进入下一次运行。
- 每次运行冻结参数、观测和SHA256。Redis任务由独立worker计算，写DB与共享产物卷；输入修改不会改写历史结果。
- 负责人复核不可覆盖；审计记录登录、数据改动、批量更正、排队、复核与导出；240请求/分钟限流、全局可恢复错误。

## 快速启动
```bash
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```
访问 http://localhost:18241 ，API http://localhost:19241/docs 。数据库映射 17741。无需Node构建。可以从中文和带空格目录启动。清理 `docker compose down -v --remove-orphans` 会删除本题演示数据卷。

|角色|账号|密码|权限与典型动作|
|---|---|---|---|
|admin 负责人|admin@demo.local|Research2026!|全部读写、批准复核、下载|
|analyst 分析师|analyst@demo.local|Research2026!|数据修改、创建任务、读取结果及下载；不能复核|
|viewer 观察员|viewer@demo.local|Research2026!|只读；仅可导出已复核结果|

## 一天的工作剧本
1. 09:00 admin登录，查“砚田·薄膜一轮”。
2. 09:10 analyst核对 `seal-fisher-202611-1.csv` 的seed记录。
3. 09:15 来源录入页检查 `工艺组 (A/B)` 等业务字段，必要时编辑。
4. 09:20 分析执行页保留默认参数 `{"alpha": 0.05}`，命名本轮研究。
5. 09:21 冻结输入并排队，worker实算，结果页自动刷新。
6. 09:25 阅读核心数值、方法边界、明细与SHA256；发现失败先修数据重跑。
7. 09:35 admin打开业务复核，写明限制与下一步动作，归档后不可覆盖。
8. 09:40 viewer读取复核意见并下载CSV，在操作留痕页核对下载事件。

seed提供3次试封试验×2个工艺组，共6条汇总计数，代表600份独立试件；另附“砚田·货架留样一轮”180件逐件记录（含迟入组、破包、失访与仍在观察）。每次试封运行每组只允许一条预聚合记录；修正计数应编辑原记录，重复组会明确失败。

货架留样剧本：来源录入页选中“砚田·货架留样一轮”，按件核对入组日与首次结局；若同一次更正涉及A与B，使用“暂存→提交整批更正”一次生效；分析执行页填指定日（默认30天）并冻结，结果页显示 B减A漏封风险差、两组指定日在险件数；若指定日无在险观察或超5秒，运行以 failed 明确拒绝并给出原因。

## 技术与目录
|部分|实现|
|---|---|
|前端|原生ES modules、HTML/CSS、Nginx1.27，无前端框架|
|API|Python3.11、FastAPI0.115、SQLAlchemy2、JWT、PBKDF2密码|
|计算|NumPy2.2、SciPy1.15，固定seed42|
|数据库|MySQL8|
|任务|Redis7持久队列，Python独立worker，心跳healthcheck|

`frontend/src/`分api、stores、types、components/common、hooks、pages、router、utils、constants；`backend/src/`分config、models、schemas、services、controllers、routes、middlewares、utils、constants；`backend/src/services/competing_risk.py`实现货架期竞争风险，`backend/src/services/algorithm.py`保留试封Fisher路径；`backend/scripts/seed_demo.py`自然键插入、重复不覆盖修改；`backend/migrations/README.md`说明schema版本。

环境变量 `.env.example`：COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、DB_PASSWORD、JWT_SECRET、SEED_DEMO。开发时在本地venv安装backend/requirements.txt，设置DATABASE_URL、REDIS_URL、JWT_SECRET再运行uvicorn；前端开发经Nginx代理 `/api/` 到不带前缀的API。

共享枚举：角色admin/analyst/viewer和队列queued/running/completed/failed；后端`src/constants/enums.py`、认证与worker使用相同值；前端`src/types/enums.js`、状态与角色界面使用相同值。Google Fonts：Noto Serif SC + IBM Plex Mono；断网使用serif/monospace回退。

## 算法输入、失败态与复现
输入为选定批次全部观测和参数，输出核心数值、明细、解释；参数经后端严格白名单和范围验证。两组试件独立，组别预先固定。双侧 p 值是固定边际下概率不大于观察表的所有表之和。。空批次拒绝；不完整字段/非有限数/非法计数拒绝；常量相关列与不足样本使任务failed并保留错误。固定seed42、输入checksum相同可复现。独立oracle：2×2固定边际对scipy fisher_exact；零格与计数非法拒绝。

已知边界：小型本地研究应用，使用合成数据，不含企业SSO与外发邮件；结果由人工复核，不自动执行业务决策；单worker恢复queued/running任务，数据库与Redis间未采用分布式事务。以当前测试目录TESTING.md记录实际验证结果。

货架留样的输入校验：`group ∈ {A,B}`；入组日不早于0；漏封/破包/失访至多录一个首次结局，且不得早于入组日；仍在观察的行三个结局都留空。指定日必须为有限非负数且不大于1,000,000。竞争风险以逐项独立重算的 Aalen-Johansen 作 oracle，覆盖迟入组、同刻事件、同刻失访、竞争事件、无在险拒绝与超时拒绝。后端测试在 `backend/tests/`，按 `backend/requirements-dev.txt` 安装后运行 `python -m pytest tests`，测试自带 SQLite 与假 Redis。

MIT License。
