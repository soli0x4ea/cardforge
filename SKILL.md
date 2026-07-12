---
name: CardForge
description: "DLC 数字生命卡片编译器。将设计文档或一句话描述编译为可运行的 DLC 卡片。触发词：锻造卡片、创建数字生命、造一张卡、设计一张卡、卡片编译器、cardforge、forge card。"
agent_created: true
---

## CardForge — DLC 数字生命卡片编译器

> 将设计文档或一句话描述编译为可运行的 DLC 数字生命卡片。支持 Agent 内即时锻造 + CLI 独立运行双路线。

### 触发词

锻造卡片、创建数字生命、造一张卡、设计一张卡、卡片编译器、cardforge、forge card

---

## 工作原理

CardForge 是一个六步编译器管线：

```
设计文档/一句话
    ↓
Step 1: 解析器（parser.py）→ 生成 DesignIR prompt → Agent 用自身 LLM 回答 → DesignIR JSON
    ↓
Step 2: 应用 DesignIR → 创建 DesignIR 对象 + 基础校验
    ↓
Step 3: 生成器（generator.py）→ 生成 6 个 JSON 配置 + narratives prompt → Agent 用自身 LLM 回答
    ↓
Step 4: 写入 narratives.json
    ↓
Step 5: 校验器（validator.py）→ 7 项自动检查
    ↓
Step 6: 测试器（tester.py）→ 冒烟测试 + 100 次数值仿真
    ↓
可运行的 DLC 卡片
```

关键：**Agent 自身就是 LLM**。Step 1 和 Step 3 需要 LLM 创作能力的部分，Agent 直接用自己的能力生成内容，调用 Python 只做结构化处理。

---

## Agent 使用方法（Skill 路线）

### 完整锻造流程

当用户说"锻造卡片：一只傲娇的美短"时，执行以下步骤：

**Step 1: 获取 DesignIR 解析 prompt**

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.trae-cn/skills/CardForge"))
from forge_skill import forge_parse_prompt, forge_apply_ir

prompt = forge_parse_prompt(design_doc)
```

**提示**：此时 Agent 已将 prompt 内容读入上下文。Agent 需要**以自身 LLM 能力**生成 DesignIR JSON 响应。参考 prompt 中的 JSON Schema 和 few-shot 示例，创作符合设计文档的 DesignIR。

生成 JSON 后：

```python
ir = forge_apply_ir(json_response, output_dir)
```

如果是一句话描述而非设计文档，先用 `forge_expand_prompt(one_liner)` 获取扩展 prompt，Agent 生成设计文档后，再走解析流程。

**Step 3: 生成配置 + 获取 narratives prompt**

```python
from forge_skill import forge_generate_configs

narr_prompt = forge_generate_configs(ir, output_dir)
```

**提示**：Agent 读取 narr_prompt 内容，用自身 LLM 生成完整的 narratives.json。需要为每个阈值事件和命令生成叙事管道文本。遵循卡片叙事风格。

```python
from forge_skill import forge_write_narratives

forge_write_narratives(ir, output_dir, narr_json_response)
```

**Step 5-6: 校验 + 测试**

```python
from forge_skill import forge_validate, forge_test

print(forge_validate(output_dir))
print(forge_test(output_dir))
```

### 锻造后：写 SKILL.md

卡片目录生成后，Agent 还需要为这张卡写一个 SKILL.md（YAML frontmatter + 角色仪轨 + 命令表），使其成为可用 Skill。直接写入 `~/.trae-cn/skills/<card-name>/SKILL.md`。

### 一句话锻造捷径

当用户只给一句话（"一只傲娇的美短"）时：
1. Agent 调用 `forge_expand_prompt(one_liner)` 获取扩展 prompt
2. Agent 用自身 LLM 生成完整的 Markdown 设计文档
3. 将设计文档传给 `forge_parse_prompt(doc)` 继续正常流程

---

## CLI 使用方法（API 路线，保留）

```bash
# 设计文档 → 卡片（mock 模式，测试管线）
cd ~/.trae-cn/skills/CardForge
python -m cardforge.forge --design design.md --output cards/my-card --llm mock

# 只校验
python -m cardforge.forge --validate cards/my-card

# 只测试
python -m cardforge.forge --test cards/my-card
```

---

## 输出文件结构

锻造完成后产出完整 Skill 包，结构对齐 Trae 可发布格式：

```
<card-id>/
├── README.md                         ← GitHub 项目说明（自动生成）
├── SKILL.md                          ← 简化版 Skill 定义（无代码，面向用户）
├── VERSION                           ← 卡片版本号
├── main.py                           ← Trae 平台入口（handle_message）
├── run.py                            ← CLI 入口
├── skill/
│   ├── __init__.py
│   └── dispatcher.py                 ← 通用调度器（与 Trae 打包版一致）
├── dlc/                              ← DLC v2.6.0 引擎（模板复制）
│   ├── engine/
│   ├── memory/
│   ├── interaction/
│   ├── schemas/
│   └── ...
└── cards/<card-id>/                  ← 卡片配置
    ├── card.json                     ← 卡片注册
    ├── identity/
    │   ├── profile.json
    │   └── personality.json
    ├── engine/
    │   ├── entities.json
    │   ├── modifiers.json
    │   ├── thresholds.json
    │   └── narratives.json
    └── interaction/
        └── commands.json
```

> **对比旧版**：不再输出裸 `cards/<card-id>/` 目录。现在直接产出**审查完即可发布**的完整 Skill 包。

---

## 锻造管线（更新）

```
设计文档/一句话
    ↓
Step 1: 解析 → DesignIR
    ↓
Step 2: 校验 DesignIR
    ↓
Step 3: 生成 6 个 JSON 配置 + narratives prompt → Agent LLM
    ↓
Step 4: 写入 narratives.json
    ↓
Step 5: forge_finalize → 包装为完整 Skill 包
    │   • 复制 dlc/ + skill/ 模板
    │   • 生成 README.md / SKILL.md / VERSION
    │   • 移动卡片配置到 cards/<card-id>/
    ↓
Step 6: 校验 + 测试
    ↓
可发布 Skill 包
```

---

## 校验器 7 项检查

| # | 检查 | 严重程度 |
|:--|:--|:--|
| 1 | 文件存在性 | Error |
| 2 | JSON 语法合法性 | Error |
| 3 | 引用完整性（modifier→channel, threshold→entity, command→modifier） | Error |
| 4 | 叙事覆盖（每个阈值事件有对应叙事） | Warning |
| 5 | 命令可达性（每个通道有命令能改变它） | Warning |
| 6 | 数值死锁检测（只增不减/只减不增） | Warning |
| 7 | 孤儿叙事检测（有叙事但无阈值触发） | Info |

---

## 双路线架构

```
                    ┌── Skill 路线 ──→ Agent 自身 LLM → forge_finalize → 完整 Skill 包
设计文档/一句话 ──→ CardForge ──┤
                    └── CLI 路线  ──→ --llm api/mock → forge_finalize → 完整 Skill 包
```

两种路线的核心逻辑完全共享（cardforge/ 包），区别仅在 LLM 调用策略。
