# -*- coding: utf-8 -*-
"""生成器 — 后端层：Design IR → DLC 卡片配置文件。

分步生成策略（每一步的 LLM 输出作为下一步的上下文）：
Step 1: card.json + identity/
Step 2: entities.json
Step 3: modifiers.json + thresholds.json
Step 4: narratives.json + commands.json
"""

import json
import os
from typing import Optional
from .design_ir import DesignIR, Complexity, Archetype

def _get_version():
    """读取 VERSION 文件，避免循环导入"""
    try:
        from pathlib import Path
        vf = Path(__file__).parent.parent / "VERSION"
        if vf.exists():
            return vf.read_text().strip()
    except Exception:
        pass
    return "1.1.2"


def generate_card_json(ir: DesignIR) -> dict:
    """Step 1: 生成 card.json + identity/ 配置。

    不需要 LLM — DesignIR 已经有足够信息直接映射。
    """
    config = {
        "card_id": ir.card_id,
        "card_name": ir.card_name,
        "protocol_version": "2.6.0",
        "version": _get_version(),
        "complexity_level": ir.complexity.value,
        "author": "cardforge",
        "created_at": "2026-07-11T00:00:00Z",
        "updated_at": "2026-07-11T00:00:00Z",
        "description": ir.description,
        "type": ir.archetype.value,
        "modules": _build_modules(ir),
    }
    return config


def generate_identity(ir: DesignIR) -> dict:
    """Step 1: 生成 identity/ 配置（profile.json + personality.json）。"""
    profile = {
        "name": ir.identity.name,
        "role": ir.identity.role,
        "description": ir.identity.description,
        "background": ir.identity.background,
    }

    personality = {
        "traits": [{"trait": t, "score": 0.7} for t in ir.identity.personality_traits],
        "speech_style": {
            "description": ir.identity.speech_style,
            "default_tone": ir.narratives.tone or "自然",
        },
        "archetype": ir.archetype.value,
    }

    return {"profile": profile, "personality": personality}


def generate_entities_json(ir: DesignIR) -> dict:
    """Step 2: 生成 entities.json。DesignIR 已有完整通道信息，直接映射。"""
    entities = {}
    for e in ir.entities:
        channels = {}
        for ch in e.channels:
            channels[ch.channel_id] = {
                "initial": ch.initial,
                "min": ch.min_val,
                "max": ch.max_val,
                "description": ch.description,
            }
        flags = {}
        for f in e.flags:
            flags[f] = False
        entities[e.entity_id] = {
            "channels": channels,
            "flags": flags,
        }
    return {"entities": entities}


def generate_modifiers_json(ir: DesignIR) -> dict:
    """Step 3: 生成 modifiers.json。DesignIR 已有完整 modifier 定义，直接映射。"""
    modifiers = {}
    for m in ir.modifiers:
        effects = {}
        for eff in m.effects:
            effects[eff.channel_id] = {
                "type": eff.operation,
                "base": eff.base,
                "random": eff.random,
            }
        modifiers[m.modifier_id] = {
            "description": m.description,
            "effects": effects,
        }
    return {"modifiers": modifiers}


def generate_thresholds_json(ir: DesignIR) -> dict:
    """Step 3: 生成 thresholds.json。DesignIR 已有完整阈值定义，直接映射。"""
    thresholds = {}
    for t in ir.thresholds:
        thresholds[t.threshold_id] = {
            "threshold_id": t.threshold_id,
            "entity": t.entity,
            "channel": t.channel,
            "operator": t.operator,
            "value": t.value,
            "cooldown_ticks": t.cooldown_ticks,
            "event_id": t.event_id,
            "event_type": t.event_type,
        }
    return {"thresholds": thresholds}


def generate_commands_json(ir: DesignIR) -> dict:
    """Step 4: 生成 commands.json。DesignIR 已有完整命令定义，直接映射。

    v2.6.0: 自动为每个命令注入 command_narrative effect（如果 DesignIR 未包含）。
    这确保命令不仅有数值效果（modifier），还会渲染叙事文本（command_narrative）。
    这是 C-01 根源 bug 的修复——CardForge 锻造的所有卡片从此不再缺文本输出。
    """
    commands = []
    for c in ir.commands:
        effects = list(c.effects) if c.effects else []

        # 自动注入 command_narrative effect（如果缺失）
        has_narrative = any(
            isinstance(e, dict) and e.get("type") == "command_narrative"
            for e in effects
        )
        if not has_narrative:
            effects.append({"type": "command_narrative", "command_id": c.command_id})

        commands.append({
            "id": c.command_id,
            "triggers": c.triggers,
            "description": c.description,
            "effects": effects,
            "cooldown_ticks": c.cooldown_ticks,
        })
    return {"commands": commands}


def build_narratives_prompt(ir: DesignIR) -> str:
    """Step 4: 生成 narratives.json 的 LLM prompt。

    narratives.json 是最需要 LLM 创作能力的部分——需要为每个命令的
    command_assembly 和每个阈值事件生成具体的叙事 pipeline 文本。

    Args:
        ir: 已填充的 DesignIR。

    Returns:
        LLM prompt — 调用方将 prompt 发给 LLM，LLM 返回 narratives.json 内容。
    """
    # 收集需要生成叙事的所有事件和命令
    events = [
        {"event_id": t.event_id, "event_type": t.event_type,
         "threshold": t.threshold_id, "channel": t.channel, "value": t.value,
         "entity": t.entity}
        for t in ir.thresholds
    ]

    cmd_ids = ir.narratives.command_assembly or [c.command_id for c in ir.commands]
    cmds = [
        {"command_id": cid, "description": next(
            (c.description for c in ir.commands if c.command_id == cid), ""
        )}
        for cid in cmd_ids
    ]

    # 通道信息（供 LLM 在叙事中引用数值变化）
    channels = []
    for e in ir.entities:
        for ch in e.channels:
            channels.append({
                "channel_id": ch.channel_id,
                "name": ch.name,
                "description": ch.description,
            })

    prompt = f"""你是一个 DLC（数字生命卡片协议）叙事设计师。请为以下卡片生成 narratives.json。

## 卡片信息

- 卡片ID: {ir.card_id}
- 名称: {ir.card_name}
- 描述: {ir.description}
- 叙事风格: {ir.narratives.style}
- 语气: {ir.narratives.tone}
- 角色名: {ir.identity.name}
- 角色性格: {', '.join(ir.identity.personality_traits)}

## 通道信息

{json.dumps(channels, ensure_ascii=False, indent=2)}

## 需要生成叙事的事件（阈值触发）

{json.dumps(events, ensure_ascii=False, indent=2)}

## 需要生成命令叙事管线的命令

{json.dumps(cmds, ensure_ascii=False, indent=2)}

## Narratives JSON 格式

```json
{{
  "events": {{
    "event_id_1": {{
      "pipeline": [
        {{
          "op": "range",
          "channel": "channel_id",
          "brackets": [
            [0, 31],
            [31, 71],
            [71, 101]
          ],
          "texts": [
            "低值叙事文本",
            "中值叙事文本",
            "高值叙事文本"
          ]
        }}
      ]
    }}
  }},
  "command_assembly": {{
    "cmd_xxx": {{
      "pipeline": [
        {{
          "op": "range",
          "channel": "channel_id",
          "brackets": [
            [0, 31],
            [31, 71],
            [71, 101]
          ],
          "texts": [
            "叙事文本1",
            "叙事文本2",
            "叙事文本3"
          ]
        }}
      ]
    }}
  }}
}}
```



**重要**：brackets 使用半开区间 [lo, hi)，相邻区间首尾相接不留间隙。例如 [0,31) + [31,71) + [71,101) 完整覆盖 [0,100] 全部取值，确保边界值 30/31/70/71/100 不会落空。

## 叙事文本创作规则

1. **每个 op 至少 2 段 texts，最多 4 段**。
2. **叙事文本应该是角色视角的**——以 {ir.identity.name} 的身份写出他/她/它感受到的、想到的、说出来的。
3. **数值变化隐含在叙事中**——不要写 "mood +10"，要写 "尾巴尖翘了起来"。
4. **文本长度 2-5 句**——太短像日志，太长像小说。
5. **贴合叙事风格**: {ir.narratives.style}
6. **事件叙事和命令叙事要区分**：事件是"发生了什么"，命令是"做了什么之后的感受变化"。

## 叙事质量检查清单

生成完 narratives.json 后，请逐条自检：

- [ ] 每个阈值事件至少有 2-3 条叙事变体（避免每次都一样）
- [ ] 叙事文本长度适中（2-5 句），不是一句话也不是一段话
- [ ] 使用了角色特有的语言风格（不是中性描述）
- [ ] 避免「你觉得」「你感到」开头——让角色直接输出感受，不翻译
- [ ] command_assembly 的 before/after 顺序正确（before → 数值变化 → after）
- [ ] range/cond/flag_check/random 四种 op 格式正确
- [ ] 高值叙事和低值叙事有明显区别（不是换几个词）
- [ ] 叙事之间有递进感（不是独立片段，而是有情绪弧线）

请输出完整的 narratives.json（events + command_assembly），不要省略任何事件或命令。"""

    return prompt


def generate_all(ir: DesignIR, output_dir: str) -> dict:
    """由 DesignIR 生成完整的 DLC 卡片目录（不需要 LLM 的部分）。

    Step 1-3 直接映射（不需要 LLM），Step 4（narratives.json）需要 LLM。
    调用方负责：
    1. 调用 generate_all() 生成 card.json / identity / entities / modifiers / thresholds / commands
    2. 调用 build_narratives_prompt(ir) 获取 prompt → 发给 LLM
    3. 将 LLM 返回的 narratives.json 写入 output_dir/engine/

    Args:
        ir: 已填充的 DesignIR。
        output_dir: 输出目录（如 cards/sticky-orange-cat）。

    Returns:
        dict: {{filename: content}} 映射（不含 narratives.json）。
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "identity"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "engine"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "interaction"), exist_ok=True)

    files = {}

    # Step 1: card.json + identity
    card = generate_card_json(ir)
    identity = generate_identity(ir)

    files[os.path.join(output_dir, "card.json")] = card
    files[os.path.join(output_dir, "identity", "profile.json")] = identity["profile"]
    files[os.path.join(output_dir, "identity", "personality.json")] = identity["personality"]

    # Step 2: entities
    entities = generate_entities_json(ir)
    files[os.path.join(output_dir, "engine", "entities.json")] = entities

    # Step 3: modifiers + thresholds
    modifiers = generate_modifiers_json(ir)
    thresholds = generate_thresholds_json(ir)
    files[os.path.join(output_dir, "engine", "modifiers.json")] = modifiers
    files[os.path.join(output_dir, "engine", "thresholds.json")] = thresholds

    # Step 4: commands (不需要 LLM，直接映射)
    commands = generate_commands_json(ir)
    files[os.path.join(output_dir, "interaction", "commands.json")] = commands
    # v2.6.0: generate body config
    body_dir = os.path.join(output_dir, "body")
    os.makedirs(body_dir, exist_ok=True)
    with open(os.path.join(body_dir, "zones.json"), "w", encoding="utf-8") as f:
        json.dump({"zones": {}}, f, ensure_ascii=False)

    # v2.6.0: generate behavior config
    if ir.complexity in (Complexity.L2, Complexity.L3):
        behav_dir = os.path.join(output_dir, "behavior")
        os.makedirs(behav_dir, exist_ok=True)
        with open(os.path.join(behav_dir, "lws_rules.json"), "w", encoding="utf-8") as f:
            json.dump({"rules": []}, f, ensure_ascii=False)


    # Write all files
    for path, content in files.items():
        with open(path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

    return files


def _build_modules(ir: DesignIR) -> dict:
    """根据复杂度构建 modules 声明。"""
    modules = {
        "identity": {
            "enabled": True,
            "profile": "identity/profile.json",
            "personality": "identity/personality.json",
        },
        "body": {"enabled": True},
        "engine": {
            "enabled": True,
            "entities": "engine/entities.json",
            "modifiers": "engine/modifiers.json",
            "thresholds": "engine/thresholds.json",
            "narratives": "engine/narratives.json",
        },
        "interaction": {
            "enabled": True,
            "commands": "interaction/commands.json",
        },
    }

    if ir.memory_enabled:
        modules["memory"] = {"enabled": True}

    if ir.complexity in (Complexity.L2, Complexity.L3):
        modules["behavior"] = {"enabled": True}

    if ir.complexity in (Complexity.L3,):
        modules["vault"] = {"enabled": True}

    return modules


def _complexity_to_int(c: Complexity) -> int:
    return {"L0": 0, "L1": 1, "L2": 2, "L3": 3}.get(c.value, 2)
