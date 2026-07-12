# CardForge Changelog

## v1.1.2 (2026-07-12) — 遗留修复

### 修复 (P0 遗留 × 1)
- **P0-4 遗留**：Frog 和 Tarot 参考卡 `narratives.command_assembly` 从 dict 改为 `list[str]`（与 Neko 一致），三张参考卡格式全部对齐

### 修复 (P1 × 1)
- **P1-5**：根目录 `__init__.py` 版本号从 `1.0.6` 同步为 `1.1.2`

### 审核依据
- 对应 [CardForge_v1.1.1_审核测试报告_20260712](report/CardForge_v1.1.1_审核测试报告_20260712.md)

---

## v1.1.1 (2026-07-12) — 审核修复

### 修复 (P0 × 4)
- **P0-1**：参考卡片 DesignIR 格式对齐 schema — personality_traits 改为 list[str]，speech_style 改为 str
- **P0-2**：`_build_skill_md` 触发词修复 — 改为从 `ir.commands[].triggers` 遍历，不再永远显示"开始"
- **P0-3**：narrative prompt 的 brackets 示例改为半开连续区间 `[0,31)` `[31,71)` `[71,101)` + 加入半开区间说明
- **P0-4**：Neko 参考卡 `narratives.command_assembly` 从 dict 改为字符串数组

### 修复 (P1 × 4)
- **P1-1**：添加 `.gitignore`（`__pycache__/`、`*.pyc` 等）
- **P1-2**：参考卡片补全 modifiers.effects（Frog 15/18、Tarot 7/7、Neko 5/17）
- **P1-3**：fallback 版本号同步为 1.1.1（forge_skill.py + generator.py）
- **P1-4**：README.md 版本号更新为 v1.1.1

### 审核依据
- 对应 [CardForge_v1.1.0_审核测试报告_20260711](report/CardForge_v1.1.0_审核测试报告_20260711.md)

---

## v1.1.0 (2026-07-11) — Phase 1 Prompt 优化

### 核心变更

本次更新对应 CardForge Skill 路线修订版 v1.1 的 Phase 1：提高生成质量。

### 修复 (P0/P1 技术债务)

- 修复: `forge_skill.py` `_build_readme` 中 `ir.triggers` 不存在 → 改为 `ir.commands` 遍历触发词
- 修复: `generator.py` 和 `forge_skill.py` 版本号硬编码 `1.0.5` → 改为从 VERSION 文件读取
- 修复: `generator.py` 导入 `__version__` 造成循环导入 → 改为独立 `_get_version()` 函数
- 清理: 删除 `templates/dlc/__pycache__/` 和所有 `.pyc` 文件

### Prompt 重写 (`parser.py`)

- 新增: DLC 核心哲学引导段落（叙事是主体，数值是配菜）
- 新增: 分步生成流程（Step 1-4，每步有校验点和前置条件）
- 新增: 三张参考卡片的通用/特有模式摘要（Neko/青蛙/塔罗）
- 新增: 数值平衡引导（delta 5-10/10-20/20-40 三档，通道 0-100）
- 改进: 设计原则从 6 条泛化规则 → 嵌入到各步骤的校验点中

### Prompt 重写 (`generator.py`)

- 新增: 叙事质量检查清单（8 项，覆盖变体数量/长度/风格/视角）
- 改进: 叙事文本长度从"30-120 字"→"2-5 句"（更直观）

### 新增文件

- `references/tarot-diviner.design_ir.json`
- `references/frog-dissection-lab.design_ir.json`
- `references/neko-cat.design_ir.json`

### 修改文件

- `cardforge/__init__.py` — 版本号 `1.0.8` → `1.1.0`
- `cardforge/parser.py` — 重写 `_build_parser_prompt`，新增 `_load_reference_summary`
- `cardforge/generator.py` — 重写 `build_narratives_prompt` 结尾段，新增 `_get_version`
- `forge_skill.py` — 修复 `ir.triggers`/版本号硬编码/循环导入
