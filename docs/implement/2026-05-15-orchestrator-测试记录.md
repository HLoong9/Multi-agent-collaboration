# Orchestrator 测试记录（2026-05-15）

## 1. 依赖安装

执行命令：

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

结果：

- 安装成功。

## 2. 单元测试

测试文件：

- `tests/test_config.py`
- `tests/test_health.py`

执行命令：

```bash
.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_health.py -v
```

结果摘要：

- `3 passed in 0.60s`

覆盖点：

1. `ORCH_` 前缀配置读取。
2. `/health` 正常分支返回 `status=ok, database=ok`。
3. `/health` 数据库异常分支返回明确错误类型。

## 3. 补充验证

执行命令：

```bash
.venv\Scripts\python.exe main.py
```

结果：

- 输出：`Orchestrator scaffold is ready.`

## 4. P3 数据模型测试（TDD）

### 4.1 RED 阶段

先新增 `tests/test_models.py`，执行：

```bash
.venv\Scripts\python.exe -m pytest tests/test_models.py -v
```

结果：

- 失败（`ImportError: cannot import name 'models' from 'app.storage'`）。

### 4.2 GREEN 阶段

实现模型与迁移后，执行：

```bash
.venv\Scripts\python.exe -m pytest tests/test_models.py -v
```

结果：

- `3 passed in 0.25s`

覆盖点：

1. 8 张核心表注册到 `Base.metadata`。
2. 通用字段 `id/created_at/updated_at` 存在。
3. 关键 JSON 字段使用 PostgreSQL `JSONB` 类型。

## 5. 全量单元测试

执行命令：

```bash
.venv\Scripts\python.exe -m pytest tests -v
```

结果：

- `6 passed in 0.42s`

## 6. 迁移离线验证

执行命令：

```bash
.venv\Scripts\python.exe -m alembic upgrade head --sql
```

结果：

- 成功输出 PostgreSQL DDL。
- 包含 `root_tasks`、`agent_tasks`、`approvals`、`artifacts`、`findings`、`suggested_actions`、`events`、`reports` 8 张表创建语句。
