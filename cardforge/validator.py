# -*- coding: utf-8 -*-
"""校验器 — 后端层：自动检查生成的 DLC 卡片质量。

纯算法，不需要 LLM。
校验维度：
1. JSON Schema — 文件是否存在、格式是否合法
2. 引用完整性 — modifier 引用的通道是否存在
3. 叙事覆盖 — 每个阈值事件是否有对应叙事
4. 命令可达 — 每个通道是否都有命令能改变它
5. 数值死锁 — 通道值是否会卡住
"""

import json
import os
from typing import Optional


class ValidationError:
    def __init__(self, check: str, message: str, severity: str = "error"):
        self.check = check
        self.message = message
        self.severity = severity  # "error" | "warning" | "info"


class ValidationReport:
    def __init__(self):
        self.errors: list[ValidationError] = []
        self.warnings: list[ValidationError] = []
        self.infos: list[ValidationError] = []

    def add(self, check: str, message: str, severity: str = "error"):
        e = ValidationError(check, message, severity)
        if severity == "error":
            self.errors.append(e)
        elif severity == "warning":
            self.warnings.append(e)
        else:
            self.infos.append(e)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def summary(self) -> str:
        lines = []
        if self.errors:
            lines.append(f"❌ {len(self.errors)} 错误")
            for e in self.errors:
                lines.append(f"   [{e.check}] {e.message}")
        if self.warnings:
            lines.append(f"⚠️ {len(self.warnings)} 警告")
            for w in self.warnings:
                lines.append(f"   [{w.check}] {w.message}")
        if self.infos:
            lines.append(f"ℹ️ {len(self.infos)} 提示")
        if not self.errors and not self.warnings:
            lines.append("✅ 全部通过")
        return "\n".join(lines)


def validate_card(card_dir: str) -> ValidationReport:
    """校验一张 DLC 卡片。

    Args:
        card_dir: 卡片目录路径（如 cards/sticky-orange-cat）。

    Returns:
        ValidationReport。
    """
    report = ValidationReport()

    # 1. 文件存在性检查
    required_files = [
        "card.json",
        "identity/profile.json",
        "identity/personality.json",
        "engine/entities.json",
        "engine/modifiers.json",
        "engine/thresholds.json",
        "engine/narratives.json",
        "interaction/commands.json",
    ]
    for rf in required_files:
        if not os.path.isfile(os.path.join(card_dir, rf)):
            report.add("file_missing", f"缺少文件: {rf}", "error")

    if not report.passed:
        return report  # 文件都不全，后续检查无意义

    # 加载所有文件
    try:
        card = _load_json(card_dir, "card.json")
        entities = _load_json(card_dir, "engine/entities.json")
        modifiers = _load_json(card_dir, "engine/modifiers.json")
        thresholds = _load_json(card_dir, "engine/thresholds.json")
        narratives = _load_json(card_dir, "engine/narratives.json")
        commands = _load_json(card_dir, "interaction/commands.json")
    except json.JSONDecodeError as e:
        report.add("json_syntax", f"JSON 语法错误: {e}", "error")
        return report

    # 2. 引用完整性检查
    _check_references(report, entities, modifiers, thresholds, commands)

    # 3. 叙事覆盖检查
    _check_narrative_coverage(report, thresholds, narratives)

    # 4. 命令可达性检查
    _check_command_coverage(report, entities, modifiers, commands)

    # 5. 数值死锁检查
    _check_deadlock(report, entities, modifiers, commands)

    return report


def _load_json(base: str, path: str) -> dict:
    with open(os.path.join(base, path), encoding="utf-8") as f:
        return json.load(f)


def _check_references(report: ValidationReport, entities, modifiers, thresholds, commands):
    """检查引用完整性。"""
    # 收集所有通道
    entities_cfg = entities.get("entities", {})
    all_channels = set()
    for eid, edata in entities_cfg.items():
        for ch_key in edata.get("channels", {}):
            all_channels.add(ch_key)

    # Modifiers → channels
    modifiers_cfg = modifiers.get("modifiers", {})
    for mid, mdata in modifiers_cfg.items():
        for ch_key in mdata.get("effects", {}):
            if ch_key not in all_channels:
                report.add("ref_integrity",
                          f"modifier {mid} 引用了不存在的通道 {ch_key}", "error")

    # Thresholds → channels + entities
    thresholds_cfg = thresholds.get("thresholds", {})
    for tid, tdata in thresholds_cfg.items():
        ch = tdata.get("channel", "")
        ent = tdata.get("entity", "")
        if ch and ch not in all_channels:
            report.add("ref_integrity",
                      f"threshold {tid} 引用了不存在的通道 {ch}", "error")
        if ent and ent not in entities_cfg:
            report.add("ref_integrity",
                      f"threshold {tid} 引用了不存在的实体 {ent}", "error")

    # Commands → modifiers
    all_modifiers = set(modifiers_cfg.keys())
    for cmd in commands.get("commands", []):
        for effect in cmd.get("effects", []):
            if effect.get("type") == "modifier":
                mid = effect.get("modifier_id", "")
                if mid and mid not in all_modifiers:
                    report.add("ref_integrity",
                              f"command {cmd.get('id')} 引用了不存在的 modifier {mid}", "error")


def _check_narrative_coverage(report: ValidationReport, thresholds, narratives):
    """检查阈值事件是否都有对应叙事。"""
    threshold_events = set()
    for tid, tdata in thresholds.get("thresholds", {}).items():
        threshold_events.add(tdata.get("event_id", ""))

    narrative_events = set(narratives.get("events", {}).keys())

    for ev_id in threshold_events:
        if ev_id not in narrative_events:
            report.add("narrative_coverage",
                      f"事件 {ev_id}（在阈值中定义）没有对应的叙事配置", "warning")

    for ev_id in narrative_events:
        if ev_id not in threshold_events:
            report.add("narrative_coverage",
                      f"叙事事件 {ev_id} 没有被任何阈值引用（孤儿叙事）", "info")


def _check_command_coverage(report: ValidationReport, entities, modifiers, commands):
    """检查每个通道是否都有命令能改变它。"""
    entities_cfg = entities.get("entities", {})
    modifiers_cfg = modifiers.get("modifiers", {})

    # 哪些通道被哪些命令影响
    channel_cmds = {}
    for ch_key in _all_channels(entities_cfg):
        channel_cmds[ch_key] = []

    for cmd in commands.get("commands", []):
        for effect in cmd.get("effects", []):
            if effect.get("type") == "modifier":
                mid = effect.get("modifier_id", "")
                mod = modifiers_cfg.get(mid, {})
                for ch_key in mod.get("effects", {}):
                    if ch_key in channel_cmds:
                        channel_cmds[ch_key].append(cmd.get("id"))

    for ch_key, cmd_list in channel_cmds.items():
        if not cmd_list:
            report.add("command_coverage",
                      f"通道 {ch_key} 没有被任何命令改变（死通道）", "warning")


def _check_deadlock(report: ValidationReport, entities, modifiers, commands):
    """检查通道是否可能死锁（只增不减或只减不增）。"""
    entities_cfg = entities.get("entities", {})
    modifiers_cfg = modifiers.get("modifiers", {})

    for eid, edata in entities_cfg.items():
        for ch_key, ch_cfg in edata.get("channels", {}).items():
            # 收集所有影响此通道的 modifier effect
            deltas = []
            for cmd in commands.get("commands", []):
                for effect in cmd.get("effects", []):
                    if effect.get("type") == "modifier":
                        mid = effect.get("modifier_id", "")
                        mod = modifiers_cfg.get(mid, {})
                        eff = mod.get("effects", {}).get(ch_key, {})
                        if eff:
                            op = eff.get("type", "add")
                            base = eff.get("base", 0)
                            if op == "add":
                                deltas.append(base)

            if not deltas:
                continue

            all_positive = all(d >= 0 for d in deltas)
            all_negative = all(d <= 0 for d in deltas)

            ch_min = ch_cfg.get("min", 0)
            ch_max = ch_cfg.get("max", 100)

            if all_positive and ch_max < 200:
                report.add("deadlock",
                          f"通道 {ch_key} 只增不减（上限 {ch_max}），可能死锁", "warning")
            if all_negative and ch_min > -100:
                report.add("deadlock",
                          f"通道 {ch_key} 只减不增（下限 {ch_min}），可能死锁", "warning")


def _all_channels(entities_cfg: dict) -> set:
    """收集所有通道 ID。"""
    channels = set()
    for eid, edata in entities_cfg.items():
        for ch_key in edata.get("channels", {}):
            channels.add(ch_key)
    return channels
