# 共享单车调度因子研究

偏相关与滞后相关的真实业务分析小型项目。完整模拟客户、痛点、上下游、算法公式与一天工作剧本见 [BUSINESS.md](BUSINESS.md)。

## 模块与业务流程
数据接入（JSON/CSV、字段验证、批次指纹）→ 观测双盲复核（冻结批次、双人背对背判定、分歧裁决、超期改派、结案生成研究批次）→ 参数化分析（异步 Python worker）→ 结果复核（指标、图形、明细、解释、批准）→ 定时分发（本地收件箱、CSV/JSON、SHA256）；另有业务总览和审计轨迹。
三个贯穿全栈的实体：Dataset 数据批次、Job 分析任务、Report 分发计划；复核批次 Review（含 ReviewItem、ReviewAssignment）把守分析入口；辅助 User、Audit、Delivery。

## 快速启动
```bash
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```
访问 http://localhost:18202；后端文档 http://localhost:19202/docs；数据库宿主端口 17702。
`SEED_DEMO=true` 自动幂等 seed；不覆盖用户修改。手动 seed 命令可重复执行。

## 演示账号与权限
|账号|密码|真实权限|
|---|---|---|
|admin@demo.local|Demo123!|接入、执行、批准、分发、暂停、读取与下载；复核改派与结案|
|analyst@demo.local|Demo123!|接入、执行、读取与下载；可发起复核；不能批准、安排分发或结案|
|viewer@demo.local|Demo123!|只读与下载；可核对复核进度与结案结论|
|reviewer1/2/3@demo.local|Demo123!|复核员：领取复核、独立交卷；互不可见对方意见|
|adjudicator@demo.local、adjudicator2@demo.local|Demo123!|裁决员：领取未参与复核的分歧条目并定案|

## 观测双盲复核
单人删改异常客流可能扭曲补车信号，因此异常观测须双盲复核后才可进入分析。
- 发起（负责人/分析员）：选定源批次与观测行号（留空为全部），发起即冻结批次快照（`frozen_records` + SHA256），之后源批次改动不影响复核。
- 领件与交卷（复核员）：每条观测由两名不同复核员独立判定保留/剔除并填写依据；双方交卷前接口与页面均隐藏彼此意见，角色权限隔离直接查询；双评一致即定案。
- 裁决（裁决员）：分歧条目仅可由未参与该条复核的裁决员领取定案，领取后可见双方匿名意见；每条分歧至多一名在办裁决员。
- 改派（负责人）：领取超期可改派，旧领取的晚到意见被拒绝，已交意见保留；被改派者不能再领同一条。
- 结案（负责人）：未齐或未裁决不结案；结案生成"研究批次 · 复核名"，仅含保留观测并附逐条依据，未复核观测默认保留；结案为幂等操作，中断重试沿用原批次且不新增；结案后停止领件，原观测与全部历史结论保留可查（非管理角色匿名）。
- 并发：领取、交卷、改派与结案均按有效领取和裁决定案，数据库行锁保证同一条目两席不重复、交卷与改派互斥。
- 演示数据自带"11月异常客流双盲复核"：按站点需求 |z| 分数挑出 12 条异常观测，含已定案、收集中和待领取条目。

## 技术与本地开发
Python 3.12 / FastAPI / SQLAlchemy / NumPy / SciPy / scikit-learn；PostgreSQL 16；Redis 7；Nginx；原生 HTML CSS JavaScript ES modules（用户指定）。后端所有校验、持久化和算法在服务端。无前端打包步骤。
后端：安装 backend/requirements.txt，设置 DATABASE_URL、REDIS_URL、JWT_SECRET、ARTIFACT_DIR 后在 backend/ 执行 `python -m migrations.initial`、`python -m scripts.seed_demo`、`uvicorn src.main:app`，另开 `python -m src.worker`。前端使用带 /api 反向代理的 Nginx，直接打开 index.html 不支持 API。

## 目录与工程约定
backend/src/{models,schemas,services,routes,controllers,middlewares,constants,config,utils}；backend/scripts/seed_demo.py；backend/migrations/initial.py。
frontend/src/{api,stores,types,components/common,hooks,pages,router,utils,constants}。
Role 枚举：admin/analyst/viewer/reviewer/adjudicator；JobStatus：queued/running/completed/failed；复核状态：Review open/closed、ReviewItem open/disputed/resolved、ReviewAssignment open/submitted/revoked。后端 backend/src/constants/enums.py，前端 frontend/src/constants/enums.js；路由权限在 middlewares/auth.py；页面按相同角色控制操作入口。

## 环境变量与 Docker
COMPOSE_PROJECT_NAME=cycle-factors；FRONTEND_PORT=18202；BACKEND_PORT=19202；DB_PORT=17702；DB_PASSWORD、JWT_SECRET 见 .env.example；SEED_DEMO 默认 true。共享命名产物卷供后端下载与 worker 写入，数据库/Redis 各持久卷。
恰好五服务均有健康检查。Redis 队列加 SQL 排队状态兜底；worker 按 next_run 生成本地收件箱文件。周期 60 秒至 30 天。分发结果为批准分析的固定快照；若需新数据重新计算并建立新计划。当前不连接邮件或企业聊天。
错误响应、请求编号、Redis 每 IP 每分钟 240 次限流、JWT 和数据库操作审计。演示密钥与密码仅供本机模拟；生产部署前配置独立密钥与账号。

## 数据与验收
所有数据为固定随机种子生成的模拟业务数据，不能作为实际生产决策证据。项目独立算法、输入边界及业务局限详见 BUSINESS.md。测试与截图统一存放 ../../test-artifacts/gb-1003/，源码不含日志/截图/测试报告。
清理本项目演示数据：`docker compose down -v --remove-orphans`（会删除本项目命名卷）。

## License
MIT，见 LICENSE。
