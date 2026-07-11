# CardForge v1.0.6 — DLC 数字生命卡片编译器

> **定位**：CardForge 是 DLC 生态的编译器。设计文档 → DesignIR → 可运行的 DLC 卡片。
>
> 关联项目：[DLC Protocol v2.6.0](https://github.com/soli0x4ea/digital-life-card)

---

## 架构

```
输入（设计文档 / 一句话描述）
    ↓
解析器（parser.py）    → DesignIR（design_ir.py）
    ↓
生成器（generator.py）  → 6 个 JSON 配置文件 + narratives.json（LLM）
    ↓
校验器（validator.py）  → 7 项自动检查
    ↓
测试器（tester.py）     → 冒烟测试 + 100 次数值仿真
    ↓
可运行的 DLC 卡片
```

## 文件说明

| 文件 | 行数 | 职责 |
|:--|:--|:--|
| `design_ir.py` | 230 | DesignIR dataclass — 编译器中间表示，含序列化/反序列化/自校验 |
| `parser.py`      | 130 | 前端 — 设计文档→IR prompt、一句话→设计文档 prompt |
| `generator.py`  | 175 | 后端 — IR→6个JSON（自动映射）+ narratives.json prompt |
| `validator.py`  | 210 | 7 项自动检查：文件存在/JSON语法/引用完整/叙事覆盖/命令可达/死锁 |
| `tester.py`     | 160 | 冒烟测试（所有命令）+ 100次随机仿真 + 边界死锁检测 |
| `forge.py`      | 275 | 主编排器 + CLI + mock LLM |

## 用法

```bash
# 设计文档 → 卡片（mock 模式，测试管线）
python -m cardforge.forge --design design.md --output cards/my-card --llm mock

# 设计文档 → 卡片（真实 LLM — 传入 llm_call 函数）
python -m cardforge.forge --design design.md --output cards/my-card --llm api

# 一句话 → 卡片（需要真实 LLM）
python -m cardforge.forge --one-liner "一只粘人的橘猫" --output cards/sticky-cat --llm api

# 只校验
python -m cardforge.forge --validate cards/my-card

# 只测试
python -m cardforge.forge --test cards/my-card
```

## 校验器 7 项检查

| # | 检查 | 严重程度 |
|:--|:--|:--|
| 1 | 文件存在性（8 个必需文件） | 错误 |
| 2 | JSON 语法合法性 | 错误 |
| 3 | 引用完整性（modifier→channel, threshold→entity, command→modifier） | 错误 |
| 4 | 叙事覆盖（每个阈值事件有对应叙事） | 警告 |
| 5 | 命令可达性（每个通道有命令能改变它） | 警告 |
| 6 | 数值死锁检测（只增不减/只减不增） | 警告 |
| 7 | 孤儿叙事检测（有叙事但无阈值触发） | 提示 |

## 已验证

- 301/301 DLC 框架测试全过
- 端到端管线：设计文档 → DesignIR → 8 个 JSON → 校验 → 8/8 冒烟通过
- 数值仿真：100 次随机命令无崩溃

## 下一步

- [ ] 接入真实 LLM API（替换 `simulate_llm`）
- [ ] 一句话描述管线（扩展+解析两步 LLM）
- [ ] 增量重编译（diff 检测）
- [ ] companion 模板
