# CardForge v1.0.8 — DLC 数字生命卡片编译器

> **会造卡片的卡片。** CardForge 本身是一张 DLC 卡片——它把设计文档/聊天记录/小说/一句话编译成可运行的数字生命卡片。
>
> 关联项目：[DLC Protocol v2.6.0](https://github.com/soli0x4ea/digital-life-card) | [塔罗牌占卜师](https://github.com/soli0x4ea/imago-explorer) | [青蛙解剖实验台](https://github.com/soli0x4ea/frog-dissection-lab)

## 🎯 在 TRAE 中体验

[📦 下载 TRAE 专用包](https://github.com/soli0x4ea/cardforge/releases/download/v1.0.8-trae/cardforge-v1.0.8-trae.zip)

> 解压后直接导入 TRAE 平台即可使用。包含完整 skill 包 + DLC v2.6.0 引擎。

---

## 为什么需要 CardForge

纯手写 Prompt 做一个 AI 角色需要 3-8 小时反复调试。DLC Protocol 把角色拆成了引擎+卡片——但手动写 JSON 配置仍然繁琐。CardForge 把最后这一段也自动化了：**写一份设计文档（或一句话），20-30 分钟出可运行的卡片。10-15x 提速。**

## 四种输入源

| 输入 | 适用场景 | 状态 |
|:--|:--|:--|
| **设计文档** | 精准创作——定义实体/通道/命令/叙事 | ✅ 可用 |
| **一句话描述** | 快速玩票——"一只高冷的黑猫" | ✅ 可用 |
| **聊天记录蒸馏** | 迁移已有角色——从对话中提取人格 | 🔜 计划中 |
| **小说/剧本抽取** | 虚构角色实体化——从文本中建卡 | 🔜 计划中 |

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

| 文件 | 职责 |
|:--|:--|
| `design_ir.py` | DesignIR dataclass — 编译器中间表示，含序列化/反序列化/自校验 |
| `parser.py` | 前端 — 设计文档→IR prompt、一句话→设计文档 prompt |
| `generator.py` | 后端 — IR→6个JSON（自动映射）+ narratives.json prompt |
| `validator.py` | 7 项自动检查：文件存在/JSON语法/引用完整/叙事覆盖/命令可达/死锁 |
| `tester.py` | 冒烟测试（所有命令）+ 100次随机仿真 + 边界死锁检测 |
| `forge.py` | 主编排器 |
| `forge_skill.py` | TRAE Skill 打包器 — 将卡片编译为可导入的 Skill 包 |

## 用法

```bash
# 设计文档 → 卡片（mock 模式，测试管线）
python -m cardforge.forge --design design.md --output cards/my-card --llm mock

# 设计文档 → 卡片（真实 LLM）
python -m cardforge.forge --design design.md --output cards/my-card --llm api

# 一句话 → 卡片
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

## DLC 生态

```
digital-life-card (v2.6.0)     ← 引擎——游戏机
    ├── imago-explorer         ← 塔罗牌占卜师
    ├── frog-dissection-lab    ← 青蛙解剖实验台
    ├── neko-cat-skill         ← Neko 电子猫
    └── cardforge              ← CardForge（你在这里）
```

## 已验证

- 301/301 DLC 框架测试全过
- 端到端管线：设计文档 → DesignIR → 8 个 JSON → 校验 → 8/8 冒烟通过
- 数值仿真：100 次随机命令无崩溃
- TRAE Skill 完整导入/运行验证通过

## 下一步

- [ ] 接入真实 LLM API（替换 `simulate_llm`）
- [ ] 聊天记录蒸馏管线
- [ ] 小说/剧本角色抽取管线
- [ ] 增量重编译（diff 检测）
