# -*- coding: utf-8 -*-
"""CardForge — DLC 数字生命卡片编译器。

主入口。协调解析器 → 生成器 → 校验器 → 测试器 的完整管线。

用法：
    # 方式一：设计文档 → 卡片
    python -m cardforge.forge --design design.md --output cards/my-card

    # 方式二：一句话 → 卡片
    python -m cardforge.forge --one-liner "一只粘人的橘猫" --output cards/sticky-cat

    # 方式三：DesignIR JSON → 卡片
    python -m cardforge.forge --ir ir.json --output cards/my-card

    # 方式四：从模板 + 人设 → 卡片
    python -m cardforge.forge --template companion --name "大橘" --persona "傲娇的橘猫" --output cards/big-orange
"""

import json
import os
import sys
import argparse
from typing import Optional

from .design_ir import DesignIR
from .parser import load_parser_prompt, load_expand_prompt
from .generator import generate_all, build_narratives_prompt
from .validator import validate_card
from .tester import run_tests


def forge_from_design(design_doc: str, output_dir: str, llm_call) -> DesignIR:
    """从设计文档编译 DLC 卡片。

    完整管线：
    1. 解析设计文档 → DesignIR（LLM）
    2. 生成配置文件（不需要 LLM）
    3. 生成 narratives.json（LLM）
    4. 校验 + 测试

    Args:
        design_doc: Markdown 设计文档。
        output_dir: 输出目录。
        llm_call: LLM 调用函数，签名为 llm_call(prompt: str) -> str（JSON 响应）。

    Returns:
        填充后的 DesignIR。
    """
    print("[CardForge] 解析设计文档 → DesignIR...")
    prompt = load_parser_prompt(design_doc)
    ir_json_str = llm_call(prompt)
    ir = DesignIR.from_dict(json.loads(ir_json_str))

    _complete_forge(ir, output_dir, llm_call)
    return ir


def forge_from_one_liner(one_liner: str, output_dir: str, llm_call) -> DesignIR:
    """从一句话描述编译 DLC 卡片。

    管线：
    1. 一句话 → 设计文档（LLM）
    2. 设计文档 → DesignIR（LLM）
    3. 生成 + narratives（LLM）
    4. 校验 + 测试

    Args:
        one_liner: 一句话描述。
        output_dir: 输出目录。
        llm_call: LLM 调用函数。

    Returns:
        填充后的 DesignIR。
    """
    print("[CardForge] 一句话 → 设计文档...")
    expand_prompt = load_expand_prompt(one_liner)
    design_doc = llm_call(expand_prompt)

    print("[CardForge] 设计文档 → DesignIR...")
    parser_prompt = load_parser_prompt(design_doc)
    ir_json_str = llm_call(parser_prompt)
    ir = DesignIR.from_dict(json.loads(ir_json_str))

    # 记录一句话作为 source
    ir.source_type = "one_liner"
    ir.source_content = one_liner

    _complete_forge(ir, output_dir, llm_call)
    return ir


def _complete_forge(ir: DesignIR, output_dir: str, llm_call):
    """完成锻造管线：生成配置 → 生成叙事 → 校验 → 测试。"""
    # Step 1-3: 生成不需要 LLM 的配置
    print(f"[CardForge] 生成配置文件 → {output_dir}...")
    generate_all(ir, output_dir)

    # Step 4: 生成 narratives.json（需要 LLM）
    print("[CardForge] 生成叙事文本 → narratives.json...")
    narr_prompt = build_narratives_prompt(ir)
    narr_json_str = llm_call(narr_prompt)
    narr_data = json.loads(narr_json_str)

    narr_path = os.path.join(output_dir, "engine", "narratives.json")
    with open(narr_path, "w", encoding="utf-8") as f:
        json.dump(narr_data, f, ensure_ascii=False, indent=2)

    # 校验
    print("[CardForge] 运行校验器...")
    report = validate_card(output_dir)
    print(report.summary())

    # 测试
    print("[CardForge] 运行测试器...")
    test_report = run_tests(output_dir)
    print(test_report.summary())

    print(f"[CardForge] ✅ 卡片已锻造完成: {output_dir}")


def simulate_llm(prompt: str) -> str:
    """本地 LLM 模拟器 — 用于测试 CardForge 管线。

    在生产环境中，这个函数会被替换为真正的 LLM API 调用。
    当前返回一个基于 prompt 内容的 mock DesignIR。
    """
    import re

    # 提取卡片名称
    name_match = re.search(r'#\s*(.+?)\n', prompt)
    card_name = name_match.group(1).strip() if name_match else "test-card"
    card_id = re.sub(r'[^a-z0-9-]', '', card_name.lower().replace(' ', '-').replace(' ', '-'))[:30]

    # 提取角色名
    identity_match = re.search(r'名称[：:]\s*(.+?)\n|角色名[：:]\s*(.+?)\n', prompt)
    identity_name = identity_match.group(1) or identity_match.group(2) if identity_match else card_name

    # 判断是一句话扩展还是解析
    if "一句话描述扩展为一份完整的设计文档" in prompt or "以下一句话描述" in prompt:
        # 这是个扩展 prompt — 返回一个空壳，让调用方循环（需要真正的 LLM）
        raise RuntimeError(
            "CardForge 需要 LLM API 来扩展一句话描述。"
            "请提供真正的 llm_call 函数，或使用 --design 模式从设计文档开始。"
        )

    # 构建最小可用 DesignIR
    ir = {
        "card_id": card_id,
        "card_name": card_name,
        "complexity": "L2",
        "archetype": "companion",
        "description": f"{card_name} — 一个自动生成的 DLC 卡片",
        "identity": {
            "name": identity_name,
            "role": card_name,
            "description": f"一个名为{identity_name}的数字生命",
            "personality_traits": ["友善", "好奇"],
            "speech_style": "自然、温暖",
            "background": "由 CardForge 自动生成",
        },
        "entities": [{
            "entity_id": "main",
            "name": identity_name,
            "description": f"{card_name}的主要实体",
            "channels": [
                {"channel_id": "mood", "name": "心情", "description": "情绪状态", "initial": 50, "min_val": 0, "max_val": 100},
                {"channel_id": "energy", "name": "精力", "description": "活力值", "initial": 70, "min_val": 0, "max_val": 100},
                {"channel_id": "trust", "name": "信任", "description": "对你的信任度", "initial": 40, "min_val": 0, "max_val": 100},
            ],
            "flags": ["is_active"],
        }],
        "modifiers": [
            {"modifier_id": "mod_hello", "description": "打招呼", "effects": [{"channel_id": "mood", "operation": "add", "base": 5}]},
            {"modifier_id": "mod_ignore", "description": "冷落", "effects": [{"channel_id": "mood", "operation": "add", "base": -5}, {"channel_id": "trust", "operation": "add", "base": -3}]},
            {"modifier_id": "mod_rest", "description": "休息", "effects": [{"channel_id": "energy", "operation": "add", "base": 20}]},
        ],
        "commands": [
            {"command_id": "cmd_hello", "triggers": ["你好", "嗨", "hello"], "description": "打招呼", "effects": [{"type": "modifier", "modifier_id": "mod_hello"}], "cooldown_ticks": 0},
            {"command_id": "cmd_ignore", "triggers": ["不理你", "走开"], "description": "冷落", "effects": [{"type": "modifier", "modifier_id": "mod_ignore"}], "cooldown_ticks": 0},
            {"command_id": "cmd_rest", "triggers": ["休息", "睡觉"], "description": "休息恢复", "effects": [{"type": "modifier", "modifier_id": "mod_rest"}], "cooldown_ticks": 5},
            {"command_id": "cmd_status", "triggers": ["状态", "怎么样"], "description": "查看状态", "effects": [], "cooldown_ticks": 0},
        ],
        "thresholds": [
            {"threshold_id": "thr_mood_high", "entity": "main", "channel": "mood", "operator": ">=", "value": 80, "event_id": "ev_mood_high", "event_type": "info", "cooldown_ticks": 10},
            {"threshold_id": "thr_mood_low", "entity": "main", "channel": "mood", "operator": "<=", "value": 20, "event_id": "ev_mood_low", "event_type": "warning", "cooldown_ticks": 10},
        ],
        "narratives": {
            "style": "自然温暖",
            "tone": "友善",
            "key_events": ["高兴时语气上扬", "低落时简短回应"],
            "command_assembly": ["cmd_hello", "cmd_ignore", "cmd_rest"],
        },
        "memory": {"enabled": False, "initial_memories": []},
        "source": {"type": "simulated", "content": "自动生成"},
    }

    return json.dumps(ir, ensure_ascii=False)


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(
        description="CardForge — DLC 数字生命卡片编译器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m cardforge.forge --design design.md --output cards/my-card
  python -m cardforge.forge --one-liner "一只粘人的橘猫" --output cards/sticky-cat
  python -m cardforge.forge --validate cards/my-card
  python -m cardforge.forge --test cards/my-card
        """,
    )

    parser.add_argument("--design", help="设计文档路径（Markdown）")
    parser.add_argument("--one-liner", help="一句话描述")
    parser.add_argument("--ir", help="DesignIR JSON 路径")
    parser.add_argument("--output", "-o", default="cards/forged-card", help="输出目录")
    parser.add_argument("--validate", help="只校验已有的卡片目录")
    parser.add_argument("--test", help="只测试已有的卡片目录")
    parser.add_argument("--llm", choices=["mock", "api"], default="mock",
                       help="LLM 调用方式: mock(模拟)/api(暂未实现)")

    args = parser.parse_args()

    # 只校验模式
    if args.validate:
        report = validate_card(args.validate)
        print(report.summary())
        sys.exit(0 if report.passed else 1)

    # 只测试模式
    if args.test:
        report = run_tests(args.test)
        print(report.summary())
        sys.exit(0 if report.passed else 1)

    # 选择 LLM 策略
    if args.llm == "mock":
        llm_call = simulate_llm
    else:
        print("[CardForge] 错误: API 模式暂未实现，请使用 --llm mock")
        sys.exit(1)

    # 设计文档 → 卡片
    if args.design:
        if not os.path.isfile(args.design):
            print(f"[CardForge] 错误: 设计文档不存在: {args.design}")
            sys.exit(1)
        with open(args.design, encoding="utf-8") as f:
            doc = f.read()
        forge_from_design(doc, args.output, llm_call)

    # 一句话 → 卡片
    elif args.one_liner:
        forge_from_one_liner(args.one_liner, args.output, llm_call)

    # DesignIR → 卡片
    elif args.ir:
        if not os.path.isfile(args.ir):
            print(f"[CardForge] 错误: IR 文件不存在: {args.ir}")
            sys.exit(1)
        with open(args.ir, encoding="utf-8") as f:
            ir = DesignIR.from_dict(json.load(f))
        _complete_forge(ir, args.output, llm_call)

    else:
        print("[CardForge] 请指定 --design / --one-liner / --ir / --validate / --test")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
