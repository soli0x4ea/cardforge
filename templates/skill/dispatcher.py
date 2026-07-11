# -*- coding: utf-8 -*-
"""DLC General-Purpose Card Dispatcher.

Loads any DLC card, processes commands via the generic engine pipeline,
persists entity state, and writes stdout. No hardcoded entity names,
channel names, or card-specific logic.

Usage:
    d = CardDispatcher("cards/tarot-v1")
    result = d.handle_message("洗牌", user_id="visitor")
"""

import os
import sys
import time
import json
from datetime import datetime
from pathlib import Path

# Ensure dlc package is importable from skill
_skill_dir = Path(__file__).resolve().parent.parent
if str(_skill_dir) not in sys.path:
    sys.path.insert(0, str(_skill_dir))

from dlc import (
    load_card, validate_card,
    CardRuntimeContext, StateManager,
    EntityState,
    match_command, execute_command, parse_input,
    CommandLoader, CommandSet,
    apply_modifier, check_thresholds, render_event,
)
from dlc.engine.narrator import render_command_narrative


# ── Tri-value channels (pain/shame/pleasure) ──────────────────
_TRI_VALUES = ("pain", "shame", "pleasure")
_TRI_LABELS = {"pain": "疼痛", "shame": "羞耻", "pleasure": "快感"}


class CardDispatcher:
    """General-purpose dispatcher for any DLC card.

    Auto-detects the primary entity from entities config.
    No Soli-specific behaviour baked in — soulchanges / emergence /
    punish-game / doodle are handled via subclass hooks or
    card-specific logic in SKILL.md.
    """

    def __init__(self, card_path: str):
        self.card_path = os.path.abspath(card_path)

        # Validate (non-fatal during development)
        try:
            validate_card(load_card(self.card_path).to_dict())
        except Exception:
            pass

        self.card = load_card(self.card_path)
        self.card_id = self.card.card_id
        self.ctx = CardRuntimeContext(self.card_path)
        self.state_mgr = StateManager(self.ctx)
        os.makedirs(self.ctx.state_dir, exist_ok=True)

        # Command set (auto-load if interaction module enabled)
        self.cmd_set: CommandSet | None = None
        if self._has_module("interaction"):
            self._load_commands()

        # Cooldowns
        self._cooldowns: dict[str, float] = {}

        # Entity states: {entity_id: EntityState}
        self._entities: dict[str, EntityState] = {}
        self._restore_entities()

    # ── Core API ──────────────────────────────────────────────

    def handle_message(self, user_input: str, user_id: str = "default") -> dict:
        """Process a user message end-to-end.

        Returns:
            {"reply": str, "command": str|None, "events": list,
             "narrative": str|None, "full_prompt": str|None, "error": str|None}
        """
        result = {"reply": "", "command": None, "narrative": None,
                  "events": [], "full_prompt": None, "error": None}

        try:
            # 1. Parse → (cmd, args)
            cmd, args = self._parse(user_input)
            if cmd is None:
                return self._fallback_reply(user_input, user_id)

            result["command"] = cmd.id

            # 2a. Meta-commands: status / reset (generic, not card-specific)
            if cmd.id in ("cmd_status", "cmd_reset", "cmd_end"):
                return self._handle_meta(cmd.id, cmd)

            # 2b. Extract intensity from args (e.g. "赐糖 3" → 3)
            intensity = self._extract_intensity(args)

            # 3. Cooldown check
            if self._is_cooling(cmd):
                result["reply"] = f"[{cmd.id}] 冷却中，请稍后再试"
                return result

            # 4. Apply effects via DLC's generic execute_command
            entity = self._get_or_create_entity(self._get_primary_entity_id())
            before = dict(entity.channels)
            before_state = EntityState(entity_id=entity.entity_id, channels=dict(before))

            outputs: list[str] = []
            events_fired: list[str] = []
            entities_cfg = self._unwrap_config(self.ctx.entities, "entities")
            modifiers_cfg = self._unwrap_config(self.ctx.modifiers, "modifiers")

            for effect in cmd.effects:
                eff = dict(effect)
                if intensity != 1.0 and eff.get("type") == "modifier":
                    eff["intensity"] = intensity

                exec_result = execute_command(
                    eff, entity,
                    modifiers_cfg=modifiers_cfg,
                    narratives_cfg=self.ctx.narratives,
                    entity_cfg=entities_cfg.get(entity.entity_id, {}),
                    before_state=before_state,
                )
                if exec_result.success and exec_result.output:
                    # Filter debug noise from state effects
                    _out = exec_result.output
                    if not (_out.startswith("flag_set:") or _out.startswith("flag_unset:")):
                        outputs.append(_out)
                if not exec_result.success and exec_result.error:
                    events_fired.append(exec_result.error)

            # 4b. Card-specific post-effects hook (soulchanges / emergence)
            hook_outputs = self._post_effects_hook(entity, before, cmd, user_input)
            outputs.extend(hook_outputs)

            # 5. Thresholds — check and render events
            thresholds_raw = self._unwrap_config(self.ctx.thresholds, "thresholds")
            seen_event_ids: set[str] = set()
            for tev in check_thresholds(entity, thresholds_raw):
                if tev.event_id in seen_event_ids:
                    continue
                text = render_event(
                    tev.event_id, self.ctx.narratives, tev.event_type,
                    entity, before_state=before_state,
                )
                if text:
                    outputs.append(text)
                    events_fired.append(tev.event_id)
                    seen_event_ids.add(tev.event_id)

            # 6. Save entity state
            self._save_entity(entity)

            # 7. Strip debug noise
            cleaned = self._strip_debug_noise(outputs)

            # 8. Build narrative text
            narrative_text = "\n".join(cleaned) if cleaned else ""

            # 9. Persist stdout (generic, all cards)
            self._write_stdout(user_input, narrative_text)

            # 10. Persist soul_changes (only if tri-value channels exist)
            self._maybe_write_soul_change(before, dict(entity.channels), cmd.id)

            # 11. Cooldown
            self._mark_used(cmd)

            result["reply"] = narrative_text
            result["narrative"] = narrative_text
            result["events"] = events_fired

        except Exception as e:
            result["error"] = str(e)
            result["reply"] = f"[错误] {e}"

        return result

    def status(self) -> dict:
        """Return current entity state summary."""
        result = {"card_id": self.card_id, "entities": {}}
        for eid, entity in self._entities.items():
            result["entities"][eid] = {
                "channels": dict(entity.channels),
                "flags": {k: v for k, v in entity.flags.items() if v},
            }
        return result

    # ── Overrideable hooks ────────────────────────────────────

    def _post_effects_hook(
        self, entity: EntityState, before: dict,
        cmd, user_input: str,
    ) -> list[str]:
        """Hook called after modifier/state effects, before thresholds.

        Override in card-specific subclasses for:
        - soulchange computation (Soli)
        - emergence task routing (Soli)
        - custom data-loading commentary
        """
        return []

    # ── Meta-commands ─────────────────────────────────────────

    def _handle_meta(self, cmd_id: str, cmd) -> dict:
        """Handle generic meta-commands (status / reset)."""
        result = {"reply": "", "command": cmd_id, "narrative": None,
                  "events": [], "full_prompt": None, "error": None}

        if cmd_id in ("cmd_status",):
            # Show current entity state
            s = self.status()
            lines = []
            for eid, edata in s["entities"].items():
                lines.append(f"[{eid}]")
                for ch, val in edata["channels"].items():
                    if val != 0:
                        lines.append(f"  {ch}: {val:.1f}")
                flags = {k: v for k, v in edata["flags"].items() if v}
                if flags:
                    lines.append(f"  flags: {', '.join(flags)}")
            result["reply"] = "\n".join(lines) if lines else "(无状态)"
            return result

        if cmd_id in ("cmd_reset", "cmd_end"):
            entity = self._get_or_create_entity(self._get_primary_entity_id())
            entities_cfg = self._unwrap_config(self.ctx.entities, "entities")
            econfig = entities_cfg.get(entity.entity_id, {})
            # Reset channels to initial values
            for ch_key, ch_cfg in econfig.get("channels", {}).items():
                val = ch_cfg.get("initial", ch_cfg.get("default", 0))
                entity.channels[ch_key] = float(val)
            # Reset flags
            for f_key, f_val in econfig.get("flags", {}).items():
                entity.flags[f_key] = f_val
            self._save_entity(entity)
            result["reply"] = "(状态已重置)"
            return result

        return result

    # ── Entity management ─────────────────────────────────────

    def _get_primary_entity_id(self) -> str:
        """Auto-detect the card's primary entity from entities config."""
        entities_cfg = self._unwrap_config(self.ctx.entities, "entities")
        if entities_cfg:
            return next(iter(entities_cfg))
        # Fallback: scan card directory for entities.json
        cfg_path = os.path.join(self.card_path, "engine", "entities.json")
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    data = json.load(f)
                entities = data.get("entities", data)
                if entities:
                    return next(iter(entities))
            except Exception:
                pass
        return "main"

    def _get_or_create_entity(self, entity_id: str) -> EntityState:
        if entity_id not in self._entities:
            entities_cfg = self._unwrap_config(self.ctx.entities, "entities")
            econfig = entities_cfg.get(entity_id, {})
            entity = EntityState(entity_id=entity_id)
            for ch_key, ch_cfg in econfig.get("channels", {}).items():
                val = ch_cfg.get("initial", ch_cfg.get("default", 0))
                entity.channels[ch_key] = float(val)
            # Initialize flags from config
            for f_key, f_val in econfig.get("flags", {}).items():
                entity.flags[f_key] = f_val
            self._entities[entity_id] = entity
        return self._entities[entity_id]

    def _save_entity(self, entity: EntityState):
        self.state_mgr.write(entity.entity_id, entity.to_dict())

    def _restore_entities(self):
        entity_ids = self.state_mgr.list_states()
        entities_cfg = self._unwrap_config(self.ctx.entities, "entities")

        if not entity_ids:
            for eid, econfig in entities_cfg.items():
                entity = EntityState(entity_id=eid)
                for ch_key, ch_cfg in econfig.get("channels", {}).items():
                    val = ch_cfg.get("initial", ch_cfg.get("default", 0))
                    entity.channels[ch_key] = float(val)
                for f_key, f_val in econfig.get("flags", {}).items():
                    entity.flags[f_key] = f_val
                self._entities[eid] = entity
            return

        for eid in entity_ids:
            data = self.state_mgr.read(eid)
            if data:
                self._entities[eid] = EntityState.from_dict(data)

        for eid, econfig in entities_cfg.items():
            if eid not in self._entities:
                self._get_or_create_entity(eid)

    # ── Persistence ───────────────────────────────────────────

    def _write_stdout(self, user_input: str, narrative_text: str):
        """Persist engine narrative to MEMORY/stdout/YYYY-MM-DD.md."""
        stdout_dir = os.path.join(self.card_path, "MEMORY", "stdout")
        os.makedirs(stdout_dir, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(stdout_dir, f"{today}.md")
        ts = datetime.now().strftime("%H:%M:%S")
        block = f"\n[{ts}] {user_input}\n{narrative_text}\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(block)

    def _maybe_write_soul_change(self, before: dict, after: dict, event: str):
        """Write soul_changes.jsonl if card has tri-value channels."""
        has_tri = any(ch in before for ch in _TRI_VALUES)
        if not has_tri:
            return

        soul_file = os.path.join(self.card_path, "MEMORY", "soul_changes.jsonl")
        os.makedirs(os.path.dirname(soul_file), exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = {
            "timestamp": ts,
            "event": event,
            "before": {ch: round(before.get(ch, 0), 1) for ch in _TRI_VALUES},
            "after": {ch: round(after.get(ch, 0), 1) for ch in _TRI_VALUES},
            "delta": {ch: round(after.get(ch, 0) - before.get(ch, 0), 1)
                      for ch in _TRI_VALUES},
        }
        with open(soul_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _unwrap_config(raw, key: str) -> dict:
        """Unwrap ctx configs that may have a top-level key wrapper."""
        if isinstance(raw, dict) and key in raw:
            return raw[key]
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _extract_intensity(args: str) -> float:
        """Extract numeric intensity from raw args string."""
        if not args:
            return 1.0
        import re
        nums = re.findall(r'\d+', args)
        try:
            return float(nums[0]) if nums else 1.0
        except (ValueError, IndexError):
            return 1.0

    def _parse(self, user_input: str):
        if self.cmd_set:
            return parse_input(user_input, self.cmd_set)
        return None, ""

    def _fallback_reply(self, user_input: str, user_id: str) -> dict:
        return {"reply": f"(未匹配到命令: {user_input})",
                "command": None, "narrative": None, "events": [], "error": None}

    def _load_commands(self):
        try:
            loader = CommandLoader(os.path.join(self.card_path, "interaction"))
            self.cmd_set = loader.load()
        except Exception:
            self.cmd_set = CommandSet()

    def _has_module(self, module: str) -> bool:
        return module in self.card.modules and self.card.modules[module].get("enabled", False)

    def _is_cooling(self, cmd) -> bool:
        if cmd.cooldown_seconds <= 0:
            return False
        last = self._cooldowns.get(cmd.id)
        return last is not None and (time.time() - last) < cmd.cooldown_seconds

    def _mark_used(self, cmd):
        self._cooldowns[cmd.id] = time.time()

    @staticmethod
    def _strip_debug_noise(outputs: list[str]) -> list[str]:
        import re as _re
        patterns = [
            _re.compile(r'^\d+\s+channel\(s\)\s+updated$'),
            _re.compile(r'^flag_toggle:'),
            _re.compile(r'^probability:'),
        ]
        cleaned = []
        for line in outputs:
            stripped = line.strip()
            if not stripped or not any(p.match(stripped) for p in patterns):
                cleaned.append(line)
        return cleaned
