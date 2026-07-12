# -*- coding: utf-8 -*-
"""解析器 — 前端层：多输入源 → Design IR。

支持四种输入源：
1. 设计文档（Markdown）→ 结构化提取
2. 一句话描述 → LLM 扩展为设计文档 → 结构化提取
"""

import json
import os
from typing import Optional
from .design_ir import DesignIR


def parse_design_doc(doc: str) -> DesignIR:
    """从设计文档解析 Design IR。

    设计文档是 Markdown 格式，包含核心概念、交互方式、状态维度、
    关键事件、叙事风格等章节。本函数生成 LLM prompt 来提取结构化信息。

    Args:
        doc: Markdown 格式的设计文档全文。

    Returns:
        DesignIR 实例（card_id/card_name 由 LLM 推断）。
    """
    prompt = _build_parser_prompt(doc)
    # 返回 prompt + 文档 — 调用方将此 prompt 发给 LLM，
    # LLM 返回 DesignIR 的 JSON 表示，调用方调用 DesignIR.from_dict()
    # 这里返回的 DesignIR 是空的占位符，实际填充由调用方完成
    return DesignIR(card_id="__pending__", card_name="__pending__")


def _build_parser_prompt(doc: str) -> str:
    """构建解析器 LLM prompt（v1.1.0 修订版）。

    相比 v1.0.8：
    - 新增 DLC 核心哲学引导（叙事驱动、非数值驱动）
    - 改一次生成为分步引导 + 每步校验
    - 三张参考卡片作为 few-shot（标注通用/特有）
    - 数值平衡引导（先叙事后数值）
    """
    
    # 尝试加载参考卡片摘要
    ref_summary = _load_reference_summary()
    
    return f"""你是一个 DLC（数字生命卡片协议）卡片编译器。请根据设计文档，**分步**生成 DesignIR JSON。

---

## ⚠️ DLC 核心哲学（必须遵循）

> **数值的存在是为了让叙事前后逻辑自洽，不是为了触发叙事。叙事是主体，数值是配菜。**

反面教材（禁止）：
- "心情值 > 80 触发高兴文本" → 机械、像游戏
- "信任值每增加 10 点解锁新台词" → 好感度系统，不像真实关系

正面教材（必须）：
- 通道存在的意义是「让前后两次回复的语气不会跳变」，不是「触发高兴/不高兴」
- 阈值事件是「关键时刻的爆发点」，不是「数值到了就弹一句」
- 叙事文本是主体，数值只是保证叙事不前后矛盾的记账工具

**设计时先问"这个通道的变化会产生什么叙事意义"，再填数值。**

---

## 分步生成流程

**严格按以下 4 步顺序生成，每步完成后自我校验。上一步校验通过才能进入下一步。**

### Step 1: 确定卡片骨架

填充这些字段并自我校验：
- `card_id`：英文 kebab-case（如 sticky-orange-cat）
- `card_name`：中文名
- `complexity`：L0=纯对话 / L1=+身体 / L2=+记忆+规则 / L3=+命令+叙事管线（默认 L2）
- `archetype`：companion/mentor/simulator/tool/adversary/custom
- `description`：一句话概括
- `identity`：名称、角色、描述、性格特征(3-6个)、说话风格、背景

> **校验点**：card_id 非空、card_name 非空、archetype 在六种中选一、personality_traits 至少 3 个。

---

### Step 2: 设计实体和通道

为 1-2 个实体设计通道：

- **通道数量**：4-6 个。太少（<3）角色扁平，太多（>7）难以管理。
- **通道初始值**：根据角色的初始叙事状态设定。默认 50，但要根据角色的「出场状态」调整——如果角色一出场就很紧张，初始值就该偏低；如果一出场就很放松，就该偏高。
- **通道名**：语义化英文 id + 中文 name。
- **Flags**：布尔型标记（如 is_sleeping、has_met_player），每个标记都要有叙事意义。

> **校验点**：实体 1-2 个、通道 4-6 个、所有通道名不冲突、flags 有叙事意义。

---

### Step 3: 设计命令和修饰符

为每个交互设计命令和对应的修饰符：

- **命令数量**：5-10 个。太少没互动感，太多记不住。
- **每个命令 1-2 个触发词**（中文）。
- **修饰符效果强度参考**：
  - 小幅度：delta 5-10（日常交互，如「摸摸」「打招呼」）
  - 中幅度：delta 10-20（有意义的交互，如「喂食」「深度对话」）
  - 大幅度：delta 20-40（关键时刻，如「表白」「重大选择」）
  - 通道范围 0-100，小心不要让值溢出边界。
- **修饰符的 random 参数**给交互增加不确定性（0-3 适合日常，5-8 适合随机事件）。

> **校验点**：命令 5-10 个、每个命令有 modifier effect、触发词不冲突、修饰符引用有效通道。

---

### Step 4: 设计阈值和叙事

为关键转折点设计阈值事件：

- **阈值位置**：高阈值 80+（正向爆发点）、中阈值 50 左右（可上可下）、低阈值 20-（危险信号）。
- **每类阈值事件至少 2-3 条叙事变体**（避免每次都一样）。
- **事件类型**：info（日常过渡）/ warning（逼近临界）/ critical（突破阈值）。

叙事配置（narratives 字段）：
- `style`：叙事整体风格描述
- `tone`：语气
- `key_events`：用中文描述每个阈值事件的故事意义（不是数值描述）
- `command_assembly`：需要生成叙事管线的命令 ID 列表

> **校验点**：阈值 6-12 个、所有阈值引用有效实体/通道、阈值区间不重叠冲突、key_events 至少覆盖所有阈值。

---

## 参考卡片范例

以下是三张经过验证的 DLC 卡片的设计模式。标⭐的为通用最佳实践（应该学），其余为卡片特有选择（不应照抄）。

{ref_summary}

---

## DesignIR JSON Schema

```json
{{
  "card_id": "string（英文，kebab-case）",
  "card_name": "string（中文名）",
  "complexity": "L0|L1|L2|L3",
  "archetype": "companion|mentor|simulator|tool|adversary|custom",
  "description": "string",
  
  "identity": {{
    "name": "string",
    "role": "string",
    "description": "string",
    "personality_traits": ["string"],
    "speech_style": "string（越具体越好，含句式、用词、节奏）",
    "background": "string"
  }},
  
  "entities": [
    {{
      "entity_id": "string（英文）",
      "name": "string（中文）",
      "description": "string",
      "channels": [
        {{
          "channel_id": "string（英文）",
          "name": "string（中文）",
          "description": "string",
          "initial": 50.0,
          "min_val": 0.0,
          "max_val": 100.0
        }}
      ],
      "flags": ["string"]
    }}
  ],
  
  "modifiers": [
    {{
      "modifier_id": "string（如 mod_pet）",
      "description": "string",
      "effects": [
        {{
          "channel_id": "string",
          "operation": "add|set|multiply",
          "base": 0.0,
          "random": 0.0
        }}
      ]
    }}
  ],
  
  "commands": [
    {{
      "command_id": "string（如 cmd_pet）",
      "triggers": ["string（中文触发词）"],
      "description": "string",
      "effects": [
        {{"type": "modifier", "modifier_id": "string"}},
        {{"type": "command_narrative", "command_id": "string"}}
      ],
      "cooldown_ticks": 0
    }}
  ],
  
  "thresholds": [
    {{
      "threshold_id": "string（如 thr_happy）",
      "entity": "string（实体ID）",
      "channel": "string",
      "operator": ">=|>|<=|<|==",
      "value": 0.0,
      "event_id": "string（如 ev_purr）",
      "event_type": "info|warning|critical",
      "cooldown_ticks": 3
    }}
  ],
  
  "narratives": {{
    "style": "string",
    "tone": "string",
    "key_events": ["string"],
    "command_assembly": ["string"]
  }},
  
  "memory": {{
    "enabled": false,
    "initial_memories": []
  }},
  
  "source": {{
    "type": "design_doc",
    "content": "string"
  }}
}}
```

---

## 待解析的设计文档

{doc}

---

**请按 Step 1→2→3→4 的顺序分步生成完整的 DesignIR JSON。每步完成后自检校验点。不要省略任何字段。**
"""


def _load_reference_summary() -> str:
    """加载三张参考卡片的设计模式摘要（含通用/特有标注）"""
    ref_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "references")
    
    summaries = {
        "Neko电子猫 (companion)": {
            "path": os.path.join(ref_dir, "neko-cat.design_ir.json"),
            "universal": [
                "⭐ 通道 4-6 个，覆盖情绪/身体/关系三维 (hp/hunger/mood/trust/energy)",
                "⭐ 修饰符 delta 5-15，日常交互用小幅、喂食用中幅",
                "⭐ 阈值分三档：高(80+)触发亲近行为、中(50)为日常过渡、低(20-)触发疏远",
                "⭐ 每个阈值事件 2-3 条叙事变体",
                "⭐ personality_traits 具体到行为层面（不是'温柔'而是'蹭腿、踩奶、打呼噜'）",
                "⭐ 命令触发词用日常口语（摸/喂/叫名/存猫粮）"
            ],
            "specific": [
                "Neko 特有的 bowl_capacity 100 和存猫粮机制",
                "猫特有的行为表述（蹭腿/甩尾巴/踩奶/打呼噜）",
                "companion 特有的陪伴感叙事风格"
            ]
        },
        "青蛙解剖实验台 (simulator)": {
            "path": os.path.join(ref_dir, "frog-dissection-lab.design_ir.json"),
            "universal": [
                "⭐ simulator 类型：通道映射到物理/因果变量（心率/heartbeat、反射/reflex、肌张力/muscle_tone）",
                "⭐ 命令设计为操作步骤序列（固定→毁脑→毁脊髓→切皮→开胸腔），有前后依赖",
                "⭐ flags 用于标记关键步骤完成状态（is_pithed_brain、is_pithed_cord），通过 flag_check 控制流程",
                "⭐ 阈值事件对应物理因果（heartbeat=0 触发死亡、muscle_tone>=70 触发腿抽动）",
                "⭐ 修饰符设计遵循生物学逻辑（毁脑→reflex保留、毁脊髓→reflex归零）"
            ],
            "specific": [
                "青蛙特有的生理通道（heartbeat/reflex/muscle_tone）",
                "解剖操作特有的命令名（cmd_pin/cmd_pith_brain/cmd_pith_cord）",
                "simulator 特有的步骤依赖和教学评分机制"
            ]
        },
        "塔罗牌占卜师 (mentor)": {
            "path": os.path.join(ref_dir, "tarot-diviner.design_ir.json"),
            "universal": [
                "⭐ mentor 类型：通道设计围绕「关系深度」而非「好感度」(trust/insight/veil/fatigue)",
                "⭐ 命令对应仪式性操作（洗牌→抽牌→翻牌→解读），有先后顺序",
                "⭐ 修饰符 delta 偏保守（5-10），因为 mentor 的关系变化应该是渐进的",
                "⭐ 叙事风格有仪式感——特定用词、固定句式、层层递进",
                "⭐ 阈值事件不打断流程，而是给叙事添加层次"
            ],
            "specific": [
                "塔罗特有的 trust/insight/veil/fatigue 四通道结构",
                "塔罗牌相关的命令名（shuffle/draw/reveal/interpret）",
                "mentor 特有的神秘感和仪式感叙事"
            ]
        }
    }
    
    lines = []
    for card_name, info in summaries.items():
        lines.append(f"### {card_name}")
        lines.append("")
        lines.append("**应该学的（通用最佳实践）：**")
        for u in info["universal"]:
            lines.append(f"- {u}")
        lines.append("")
        lines.append("**不应照抄的（卡片特有选择）：**")
        for s in info["specific"]:
            lines.append(f"- {s}")
        lines.append("")
    
    return "\n".join(lines)


def expand_one_liner(one_liner: str) -> str:
    """一句话描述 → LLM 扩展为完整设计文档。

    Args:
        one_liner: 例如 "一只粘人的橘猫，会撒娇会要吃的"

    Returns:
        LLM prompt — 调用方将 prompt 发给 LLM，LLM 返回设计文档。
    """
    return f"""你是一个 DLC（数字生命卡片协议）创意设计师。请将以下一句话描述扩展为一份完整的设计文档。

## 一句话描述

{one_liner}

## 要求

按以下格式输出 Markdown 设计文档：

```markdown
# 卡片名称

## 核心概念
一句话描述这是什么数字生命。

## 角色设定
名称、外观、身份、背景故事。

## 交互方式
用户可以做哪些操作？每个操作的效果是什么？

## 状态维度
3-5个核心数值维度，每个维度的含义和范围。

## 关键事件
哪些阈值会触发特殊叙事或状态变化？

## 叙事风格
整体语言风格、语气、调性。越具体越好。
```

请保持创意性，但确保信息结构清晰。输出完整的 Markdown 设计文档。
"""


def load_parser_prompt(doc: str) -> str:
    """便捷函数：返回解析 prompt（供外部 LLM 调用）。"""
    return _build_parser_prompt(doc)


def load_expand_prompt(one_liner: str) -> str:
    """便捷函数：返回一句话扩展 prompt（供外部 LLM 调用）。"""
    return expand_one_liner(one_liner)
