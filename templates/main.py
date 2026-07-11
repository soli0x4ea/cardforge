# -*- coding: utf-8 -*-
"""DLC Skill Entry Point."""
import os, sys
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
os.chdir(_here)

from skill.dispatcher import CardDispatcher

def handle_message(user_input: str, user_id: str = "default") -> dict:
    """主入口：接收用户消息，返回回复。"""
    card_path = os.path.join(_here, "cards")
    # 找第一张卡片
    for name in sorted(os.listdir(card_path)):
        p = os.path.join(card_path, name)
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, "card.json")):
            card_path = p
            break
    
    d = CardDispatcher(card_path)
    result = d.handle_message(user_input, user_id=user_id)
    return {
        "reply": result.get("reply", ""),
        "narrative": result.get("narrative", ""),
        "events": result.get("events", []),
        "command": result.get("command"),
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--msg", default=None)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    
    card_path = os.path.join(_here, "cards")
    for name in sorted(os.listdir(card_path)):
        p = os.path.join(card_path, name)
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, "card.json")):
            card_path = p
            break
    
    d = CardDispatcher(card_path)
    print(f"[卡片] {d.card_id}")
    
    if args.status:
        s = d.status()
        for eid, edata in s["entities"].items():
            print(f"[实体: {eid}]")
            for ch, val in edata["channels"].items():
                print(f"  {ch}: {val:.1f}")
            flags = {k: v for k, v in edata["flags"].items() if v}
            if flags:
                print(f"  flags: {list(flags.keys())}")
    elif args.msg:
        r = d.handle_message(args.msg)
        if r.get("error"):
            print(f"[错误] {r['error']}")
        else:
            print(r["reply"] or "(无输出)")
