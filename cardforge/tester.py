# -*- coding: utf-8 -*-
"""测试器 — 后端层：自动运行冒烟测试和数值仿真。

不需要 LLM。直接加载卡片并执行所有命令。
"""

import sys
import os
from typing import Optional

# Ensure dlc/ is importable
_cardforge_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _cardforge_dir not in sys.path:
    sys.path.insert(0, _cardforge_dir)


class TestReport:
    def __init__(self):
        self.results: list[dict] = []
        self.simulation_log: list[str] = []

    def add(self, test_name: str, passed: bool, detail: str = ""):
        self.results.append({
            "test": test_name,
            "passed": passed,
            "detail": detail,
        })

    @property
    def passed(self) -> bool:
        return all(r["passed"] for r in self.results)

    def summary(self) -> str:
        lines = []
        for r in self.results:
            icon = "✅" if r["passed"] else "❌"
            detail = f" — {r['detail']}" if r["detail"] else ""
            lines.append(f"{icon} {r['test']}{detail}")
        if self.simulation_log:
            lines.append("\n-- 数值仿真 --")
            lines.extend(self.simulation_log[-10:])  # 只显示最后 10 行
        lines.append(f"\n{'全部通过' if self.passed else '存在失败'}: "
                     f"{sum(1 for r in self.results if r['passed'])}/{len(self.results)}")
        return "\n".join(lines)


def run_tests(card_dir: str) -> TestReport:
    """对一张 DLC 卡片运行冒烟测试和数值仿真。

    Args:
        card_dir: 卡片目录路径。

    Returns:
        TestReport。
    """
    report = TestReport()

    # 1. 加载卡片
    try:
        from dlc import load_card, CardRuntimeContext, EntityState
        from dlc.engine.modifier import apply_modifier
        from dlc.engine.threshold import check_thresholds
        from dlc.engine.narrator import render_command_narrative, render_event
        from dlc.interaction.commands import match_command, CommandLoader
    except ImportError as e:
        report.add("import", False, f"无法导入 DLC 框架: {e}")
        return report

    try:
        ctx = CardRuntimeContext(card_dir)
        card = load_card(card_dir)
        report.add("load_card", True, card.card_id)
    except Exception as e:
        report.add("load_card", False, str(e))
        return report

    # 2. 加载命令
    try:
        cmd_set = CommandLoader(os.path.join(card_dir, "interaction")).load()
        report.add("load_commands", True, f"{len(cmd_set.commands)} 条命令")
    except Exception as e:
        report.add("load_commands", False, str(e))
        return report

    # 3. 创建实体
    entities_cfg = ctx.entities.get("entities", {})
    modifiers_cfg = ctx.modifiers.get("modifiers", {})
    thresholds_cfg = ctx.thresholds.get("thresholds", {})
    narratives_cfg = ctx.narratives

    if not entities_cfg:
        report.add("entities", False, "无实体定义")
        return report

    primary_eid = next(iter(entities_cfg))
    econfig = entities_cfg[primary_eid]

    entity = EntityState(
        entity_id=primary_eid,
        channels={ch: cfg["initial"] for ch, cfg in econfig.get("channels", {}).items()},
        flags={f: False for f in econfig.get("flags", {})},
    )
    report.add("create_entity", True, primary_eid)

    # 4. 冒烟测试：执行每条命令
    for cmd in cmd_set.commands:
        try:
            # Match
            matched = match_command(cmd.triggers[0] if cmd.triggers else cmd.id, cmd_set)
            if not matched:
                report.add(f"smoke:match::{cmd.id}", False, f"无法通过触发词 '{cmd.triggers}' 匹配")
                continue

            # Execute effects
            for effect in cmd.effects:
                etype = effect.get("type")
                if etype == "modifier":
                    mid = effect.get("modifier_id")
                    mod = modifiers_cfg.get(mid)
                    if mod:
                        result = apply_modifier(entity, mod, entity_cfg=econfig)
                        if not result.applied:
                            report.add(f"smoke:mod::{cmd.id}::{mid}", False,
                                      f"modifier 未应用: {result.note}")
                    else:
                        report.add(f"smoke:mod::{cmd.id}::{mid}", False,
                                  f"modifier 不存在: {mid}")
                elif etype == "command_narrative":
                    cid = effect.get("command_id")
                    text = render_command_narrative(cid, entity, narratives_cfg)
                    if not text:
                        report.add(f"smoke:narr::{cmd.id}::{cid}", False,
                                  "command_narrative 返回空文本")

            # Threshold checks
            threshold_events = check_thresholds(entity, thresholds_cfg)
            for tev in threshold_events:
                render_event(tev.event_id, narratives_cfg, tev.event_type, entity)

        except Exception as e:
            report.add(f"smoke::{cmd.id}", False, f"异常: {str(e)[:80]}")
        else:
            report.add(f"smoke::{cmd.id}", True, "")

    # 5. 数值仿真：执行 100 次随机命令
    try:
        sim_entity = EntityState(
            entity_id=primary_eid,
            channels={ch: cfg["initial"] for ch, cfg in econfig.get("channels", {}).items()},
            flags={f: False for f in econfig.get("flags", {})},
        )

        max_changes = {ch: {"old": sim_entity.channels[ch]} for ch in sim_entity.channels}
        min_changes = {ch: {"old": sim_entity.channels[ch]} for ch in sim_entity.channels}

        for i in range(100):
            # Pick random command
            import random
            cmd = random.choice(cmd_set.commands)
            before = dict(sim_entity.channels)

            for effect in cmd.effects:
                if effect.get("type") == "modifier":
                    mid = effect.get("modifier_id")
                    mod = modifiers_cfg.get(mid)
                    if mod:
                        apply_modifier(sim_entity, mod, entity_cfg=econfig)

            after = dict(sim_entity.channels)
            for ch in after:
                if ch not in sim_entity.channels:
                    continue
                delta = after[ch] - before.get(ch, 0)
                if delta != 0:
                    break

        # 记录变化范围
        for ch in sim_entity.channels:
            final = sim_entity.channels[ch]
            initial = max_changes[ch]["old"]
            delta = final - initial
            report.simulation_log.append(
                f"  {ch}: {initial:.0f} → {final:.0f} (Δ={delta:+.0f})"
            )

        # 检查是否有通道卡在边界
        stuck = []
        for ch, ch_cfg in econfig.get("channels", {}).items():
            val = sim_entity.channels[ch]
            ch_min = ch_cfg.get("min", 0)
            ch_max = ch_cfg.get("max", 100)
            if val <= ch_min + 1 or val >= ch_max - 1:
                stuck.append(ch)
        if stuck:
            report.add("simulation", True,
                      f"通道 {', '.join(stuck)} 接近边界（正常，如果卡片设计中没有反方向操作的话）")
        else:
            report.add("simulation", True, "数值仿真完成，无异常")

    except Exception as e:
        report.add("simulation", False, f"仿真失败: {str(e)[:80]}")

    return report
