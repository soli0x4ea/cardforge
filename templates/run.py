# -*- coding: utf-8 -*-
"""CLI entry point for DLC card."""
import os, sys, argparse
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path: sys.path.insert(0, _here)
os.chdir(_here)

from skill.dispatcher import CardDispatcher

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", default=None)
    parser.add_argument("--msg", default=None)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    card_path = args.card
    if not card_path:
        cards_dir = os.path.join(_here, "cards")
        for name in sorted(os.listdir(cards_dir)):
            p = os.path.join(cards_dir, name)
            if os.path.isdir(p) and os.path.isfile(os.path.join(p, "card.json")):
                card_path = p  # use absolute path
                break
    if not card_path:
        print("No card found")
        sys.exit(1)

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
        return

    if args.msg:
        r = d.handle_message(args.msg)
        if r["error"]:
            print(f"[错误] {r['error']}")
        else:
            print(r["reply"] or "(无输出)")

if __name__ == "__main__":
    main()
