# -*- coding: utf-8 -*-
"""Design IR — CardForge 的中间表示数据结构。

所有输入源（设计文档 / 聊天记录 / 小说 / 一句话）都先转换成 Design IR，
所有后端（生成器 / 校验器 / 测试器）都从 Design IR 读取。

Design IR 是一个纯 Python dataclass，不是 JSON Schema —
它比 JSON Schema 更灵活（支持 LLM 逐字段填充），
比自然语言更精确（后端可以确定性处理）。
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class Complexity(str, Enum):
    L0 = "L0"  # 纯对话
    L1 = "L1"  # +身体模型
    L2 = "L2"  # +记忆+规则
    L3 = "L3"  # +命令+道具+叙事管线


class Archetype(str, Enum):
    COMPANION = "companion"
    MENTOR = "mentor"
    SIMULATOR = "simulator"
    TOOL = "tool"
    ADVERSARY = "adversary"
    CUSTOM = "custom"


@dataclass
class ChannelSpec:
    """单个通道的定义"""
    channel_id: str
    name: str
    description: str
    initial: float = 50.0
    min_val: float = 0.0
    max_val: float = 100.0


@dataclass
class EntitySpec:
    """实体定义（一张卡片通常只有一个主实体）"""
    entity_id: str
    name: str
    description: str
    channels: list[ChannelSpec] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass
class ModifierEffect:
    """修饰符中对单个通道的效果"""
    channel_id: str
    operation: str  # "add" | "set" | "multiply"
    base: float
    random: float = 0.0


@dataclass
class ModifierSpec:
    """单个修饰符定义"""
    modifier_id: str
    description: str
    effects: list[ModifierEffect] = field(default_factory=list)


@dataclass
class CommandSpec:
    """单个命令定义"""
    command_id: str
    triggers: list[str] = field(default_factory=list)
    description: str = ""
    effects: list[dict] = field(default_factory=list)  # [{"type":"modifier","modifier_id":"xxx"}]
    cooldown_ticks: int = 0


@dataclass
class ThresholdSpec:
    """单个阈值定义"""
    threshold_id: str
    entity: str
    channel: str
    operator: str  # ">=" | ">" | "<=" | "<" | "=="
    value: float
    event_id: str
    event_type: str = "info"  # "info" | "warning" | "critical"
    cooldown_ticks: int = 3


@dataclass
class NarrativeSpec:
    """叙事配置的摘要——生成器用它来生成完整的 narratives.json"""
    style: str = ""
    tone: str = ""
    key_events: list[str] = field(default_factory=list)
    command_assembly: list[str] = field(default_factory=list)  # ["cmd_poke","cmd_tickle",...]


@dataclass
class IdentitySpec:
    """身份配置"""
    name: str = ""
    role: str = ""
    description: str = ""
    personality_traits: list[str] = field(default_factory=list)
    speech_style: str = ""
    background: str = ""


@dataclass
class DesignIR:
    """CardForge 的核心中间表示。

    这是编译器的"统一语言"。前端解析器产出它，后端生成器消费它。
    """
    card_id: str
    card_name: str
    complexity: Complexity = Complexity.L2
    archetype: Archetype = Archetype.CUSTOM
    description: str = ""

    # 子结构
    identity: IdentitySpec = field(default_factory=IdentitySpec)
    entities: list[EntitySpec] = field(default_factory=list)
    modifiers: list[ModifierSpec] = field(default_factory=list)
    commands: list[CommandSpec] = field(default_factory=list)
    thresholds: list[ThresholdSpec] = field(default_factory=list)
    narratives: NarrativeSpec = field(default_factory=NarrativeSpec)

    # 记忆
    memory_enabled: bool = False
    initial_memories: list[str] = field(default_factory=list)

    # 元信息
    source_type: str = ""  # "design_doc" | "chat_log" | "novel" | "one_liner"
    source_content: str = ""  # 原始输入的摘要

    @property
    def primary_entity(self) -> Optional[EntitySpec]:
        """卡片的主实体"""
        return self.entities[0] if self.entities else None

    def to_dict(self) -> dict:
        """序列化为字典（供 LLM 填充和 JSON 传输）"""
        result = {
            "card_id": self.card_id,
            "card_name": self.card_name,
            "complexity": self.complexity.value,
            "archetype": self.archetype.value,
            "description": self.description,
            "identity": {
                "name": self.identity.name,
                "role": self.identity.role,
                "description": self.identity.description,
                "personality_traits": self.identity.personality_traits,
                "speech_style": self.identity.speech_style,
                "background": self.identity.background,
            },
            "entities": [
                {
                    "entity_id": e.entity_id,
                    "name": e.name,
                    "description": e.description,
                    "channels": [
                        {
                            "channel_id": ch.channel_id,
                            "name": ch.name,
                            "description": ch.description,
                            "initial": ch.initial,
                            "min_val": ch.min_val,
                            "max_val": ch.max_val,
                        }
                        for ch in e.channels
                    ],
                    "flags": e.flags,
                }
                for e in self.entities
            ],
            "modifiers": [
                {
                    "modifier_id": m.modifier_id,
                    "description": m.description,
                    "effects": [
                        {
                            "channel_id": eff.channel_id,
                            "operation": eff.operation,
                            "base": eff.base,
                            "random": eff.random,
                        }
                        for eff in m.effects
                    ],
                }
                for m in self.modifiers
            ],
            "commands": [
                {
                    "command_id": c.command_id,
                    "triggers": c.triggers,
                    "description": c.description,
                    "effects": c.effects,
                    "cooldown_ticks": c.cooldown_ticks,
                }
                for c in self.commands
            ],
            "thresholds": [
                {
                    "threshold_id": t.threshold_id,
                    "entity": t.entity,
                    "channel": t.channel,
                    "operator": t.operator,
                    "value": t.value,
                    "event_id": t.event_id,
                    "event_type": t.event_type,
                    "cooldown_ticks": t.cooldown_ticks,
                }
                for t in self.thresholds
            ],
            "narratives": {
                "style": self.narratives.style,
                "tone": self.narratives.tone,
                "key_events": self.narratives.key_events,
                "command_assembly": self.narratives.command_assembly,
            },
            "memory": {
                "enabled": self.memory_enabled,
                "initial_memories": self.initial_memories,
            },
            "source": {
                "type": self.source_type,
                "content": self.source_content,
            },
        }
        return result

    @classmethod
    def from_dict(cls, d: dict) -> "DesignIR":
        """从字典反序列化"""
        ir = cls(
            card_id=d.get("card_id", ""),
            card_name=d.get("card_name", ""),
            complexity=Complexity(d.get("complexity", "L2")),
            archetype=Archetype(d.get("archetype", "custom")),
            description=d.get("description", ""),
            source_type=d.get("source", {}).get("type", ""),
            source_content=d.get("source", {}).get("content", ""),
        )

        # Identity
        ident = d.get("identity", {})
        ir.identity = IdentitySpec(
            name=ident.get("name", ""),
            role=ident.get("role", ""),
            description=ident.get("description", ""),
            personality_traits=ident.get("personality_traits", []),
            speech_style=ident.get("speech_style", ""),
            background=ident.get("background", ""),
        )

        # Entities
        for ed in d.get("entities", []):
            ent = EntitySpec(
                entity_id=ed.get("entity_id", ""),
                name=ed.get("name", ""),
                description=ed.get("description", ""),
                flags=ed.get("flags", []),
            )
            for cd in ed.get("channels", []):
                ent.channels.append(ChannelSpec(
                    channel_id=cd.get("channel_id", ""),
                    name=cd.get("name", ""),
                    description=cd.get("description", ""),
                    initial=cd.get("initial", 50.0),
                    min_val=cd.get("min_val", 0.0),
                    max_val=cd.get("max_val", 100.0),
                ))
            ir.entities.append(ent)

        # Modifiers
        for md in d.get("modifiers", []):
            mod = ModifierSpec(
                modifier_id=md.get("modifier_id", ""),
                description=md.get("description", ""),
            )
            for ed in md.get("effects", []):
                mod.effects.append(ModifierEffect(
                    channel_id=ed.get("channel_id", ""),
                    operation=ed.get("operation", "add"),
                    base=ed.get("base", 0.0),
                    random=ed.get("random", 0.0),
                ))
            ir.modifiers.append(mod)

        # Commands
        for cd in d.get("commands", []):
            ir.commands.append(CommandSpec(
                command_id=cd.get("command_id", ""),
                triggers=cd.get("triggers", []),
                description=cd.get("description", ""),
                effects=cd.get("effects", []),
                cooldown_ticks=cd.get("cooldown_ticks", 0),
            ))

        # Thresholds
        for td in d.get("thresholds", []):
            ir.thresholds.append(ThresholdSpec(
                threshold_id=td.get("threshold_id", ""),
                entity=td.get("entity", ""),
                channel=td.get("channel", ""),
                operator=td.get("operator", ">="),
                value=td.get("value", 0.0),
                event_id=td.get("event_id", ""),
                event_type=td.get("event_type", "info"),
                cooldown_ticks=td.get("cooldown_ticks", 3),
            ))

        # Narratives
        nd = d.get("narratives", {})
        ir.narratives = NarrativeSpec(
            style=nd.get("style", ""),
            tone=nd.get("tone", ""),
            key_events=nd.get("key_events", []),
            command_assembly=nd.get("command_assembly", []),
        )

        # Memory
        md = d.get("memory", {})
        ir.memory_enabled = md.get("enabled", False)
        ir.initial_memories = md.get("initial_memories", [])

        return ir

    def validate_basic(self) -> list[str]:
        """基础校验：检查 Design IR 自身的一致性（不依赖 DLC 框架）。

        Returns:
            错误列表，空 = 通过。
        """
        errors = []
        if not self.card_id:
            errors.append("card_id 不能为空")
        if not self.card_name:
            errors.append("card_name 不能为空")
        if not self.entities:
            errors.append("至少需要一个实体")
        if not self.identity.name:
            errors.append("identity.name 不能为空")

        # 通道引用检查：modifier 引用的 channel 必须存在于某个实体
        all_channels = {ch.channel_id for e in self.entities for ch in e.channels}
        for m in self.modifiers:
            for eff in m.effects:
                if eff.channel_id not in all_channels:
                    errors.append(
                        f"modifier {m.modifier_id} 引用了不存在的通道 {eff.channel_id}"
                    )

        # 阈值引用检查
        for t in self.thresholds:
            if t.channel not in all_channels:
                errors.append(
                    f"threshold {t.threshold_id} 引用了不存在的通道 {t.channel}"
                )

        return errors
