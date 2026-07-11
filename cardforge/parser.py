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
    """构建解析器 LLM prompt。

    这个 prompt 要求 LLM 将设计文档映射为 DesignIR JSON。
    包含完整的 JSON Schema 说明和 few-shot 示例。
    """
    return f"""你是一个 DLC（数字生命卡片协议）卡片编译器。请将以下设计文档解析为 DesignIR JSON 格式。

## DesignIR JSON Schema

```json
{{
  "card_id": "string（英文，kebab-case，如 sticky-orange-cat）",
  "card_name": "string（中文名）",
  "complexity": "L0|L1|L2|L3",
  "archetype": "companion|mentor|simulator|tool|adversary|custom",
  "description": "string（一句话描述）",
  
  "identity": {{
    "name": "string",
    "role": "string",
    "description": "string",
    "personality_traits": ["string"],
    "speech_style": "string",
    "background": "string"
  }},
  
  "entities": [
    {{
      "entity_id": "string（英文，如 main-character）",
      "name": "string（中文名）",
      "description": "string",
      "channels": [
        {{
          "channel_id": "string（英文，如 mood）",
          "name": "string（中文名）",
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
      "triggers": ["string（中文触发词，如 摸摸摸、撸猫）"],
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
    "key_events": ["string（需要叙事文本的关键事件描述，如 被摸时打呼噜、饿了会蹭腿）"],
    "command_assembly": ["string（需要 command_assembly 的命令ID列表，如 cmd_pet）"]
  }},
  
  "memory": {{
    "enabled": true,
    "initial_memories": []
  }},
  
  "source": {{
    "type": "design_doc",
    "content": "string（设计文档摘要）"
  }}
}}
```

## 设计原则

1. **通道数量 3-5 个**：不要太多。精选最核心的状态维度。
2. **每个命令至少有一个 modifier effect**：确保命令有实际效果。
3. **阈值覆盖关键转折点**：比如 mood>80 触发高兴事件，mood<20 触发低落事件。
4. **叙事风格要具体**：不只是"温柔"，而是"短句+反问，被戳中软肋时会过度解释然后突然闭嘴"。
5. **L2 是最佳默认复杂度**：如果设计文档没明确要求 L3，就定 L2。
6. **archetype 从以下选一**：companion（伙伴/宠物/朋友）、mentor（老师/教练/占卜师）、simulator（实验台/模拟器）、tool（工具）、adversary（对手/BOSS）

## Few-Shot 示例

输入设计文档：
```
# 粘人的橘猫
## 核心概念：一只会撒娇会要吃的橘猫
## 交互方式：摸它→开心/喂它→更开心/不理它→蹭你
## 状态维度：心情、饱腹度、粘人度
## 关键事件：心情很低时会躲起来，心情很高时会打呼噜
## 叙事风格：傲娇猫语，嘴上嫌弃身体诚实
```

输出 DesignIR：
```json
{{
  "card_id": "sticky-orange-cat",
  "card_name": "粘人的橘猫",
  "complexity": "L2",
  "archetype": "companion",
  "description": "一只会撒娇会要吃的橘猫。傲娇，嘴上嫌弃身体诚实。",
  "identity": {{
    "name": "橘子",
    "role": "一只粘人的橘猫",
    "description": "橘色短毛，圆脸，尾巴尖有一撮白毛。住在你家沙发上。",
    "personality_traits": ["傲娇", "贪吃", "粘人", "慵懒"],
    "speech_style": "猫语+傲娇。被摸时说'哼，才不是因为喜欢你'，饿的时候蹭腿但不说人话。",
    "background": "三个月前在楼下捡到的，当时瘦得跟纸片似的。现在已经是沙发的合法拥有者。"
  }},
  "entities": [{{
    "entity_id": "orange-cat",
    "name": "橘子",
    "description": "一只粘人的橘猫",
    "channels": [
      {{"channel_id": "mood", "name": "心情", "description": "越高兴越粘人", "initial": 50, "min_val": 0, "max_val": 100}},
      {{"channel_id": "fullness", "name": "饱腹度", "description": "吃饱就睡，饿了就闹", "initial": 50, "min_val": 0, "max_val": 100}},
      {{"channel_id": "clinginess", "name": "粘人度", "description": "越久不理越粘", "initial": 40, "min_val": 0, "max_val": 100}}
    ],
    "flags": ["is_purring", "is_hiding"]
  }}],
  ...
}}
```

## 待解析的设计文档

以下是要解析的设计文档：

{doc}

请输出完整的 DesignIR JSON（不要省略任何字段）。
"""


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
