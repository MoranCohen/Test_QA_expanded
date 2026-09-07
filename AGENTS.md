be# Claude Code – AI Extension Reference

This file is automatically loaded at the start of every Claude Code session (project-level).
Use it to document project-specific conventions, AI extension points, and working agreements.

---

## 1. Auto-Loaded Every Session

| File | Location | What it does |
|---|---|---|
| `CLAUDE.md` | Project root & `~/.claude/CLAUDE.md` | Always injected into context. Put project conventions and permanent instructions here. |
| `MEMORY.md` | `~/.claude/projects/<project>/memory/MEMORY.md` | Index of persistent memories. Loaded every session; individual memory files loaded on demand. |
| Skill frontmatter | All `SKILL.md` files | **Name + description only** are always available so Claude knows when to activate. Full content loads lazily when the skill is triggered. |
| Settings | `.claude/settings.json` / `~/.claude/settings.json` | Permissions, hooks, env vars, model overrides. Never loaded into context — applied by the harness. |

---

## 2. Commands (User-Invoked Slash Commands)

**Location:** `.claude/commands/<name>.md` (project) or `~/.claude/commands/<name>.md` (user-global)

**Trigger:** User types `/name` explicitly.

**Format:**
```
.claude/commands/
└── review-tests.md       →  invoked via /review-tests
```

**Frontmatter options:**
```yaml
---
description: shown in /help
argument-hint: <file> [--flag]
allowed-tools: [Read, Bash, Grep]
model: sonnet
---
```

**Use for:** On-demand tasks the user explicitly triggers (code review, scaffold, report).

---

## 3. Skills (Model-Invoked or User-Invoked)

**Location:** `.claude/skills/<name>/SKILL.md` (project) or `~/.claude/skills/<name>/SKILL.md` (user-global)

**Trigger:** Claude reads the `description` field and activates automatically when the user's request matches — no slash needed. Can also be user-invoked via `/name` if frontmatter includes `argument-hint`.

**Format:**
```
.claude/skills/
└── review-tests/
    ├── SKILL.md          ← required
    ├── references/       ← optional supporting docs
    └── examples/         ← optional examples
```

**Frontmatter options:**
```yaml
---
name: review-tests
description: Use this skill when the user asks to "review tests", "audit test quality",
             or shares a pytest file and asks for feedback.
version: 1.0.0
allowed-tools: [Read, Bash, Agent]
model: sonnet
---
```

**Loading behavior:**
- `name` + `description` → always in context (lightweight, used for matching)
- Full `SKILL.md` body → loaded only when the skill activates (lazy)

**Use for:** Domain expertise Claude should apply automatically without the user remembering to ask.

---

## 4. Agents (Isolated Claude Instances)

**Spawned by:** Claude itself (via the `Agent` tool) or a Workflow script.

**Key properties:**
- Starts with a **fresh, empty context** — does not inherit the current conversation
- Can run in **parallel** with other agents
- Can be given specific tools, a model, an effort level, or a git worktree (for file isolation)
- Returns its result as text or structured JSON back to the spawner

**Common patterns:**
```
Parallel agents           → fan-out review across dimensions simultaneously
Background agents         → long-running tasks while conversation continues
Worktree-isolated agents  → agents that edit files without conflicting with each other
```

**Defined as reusable types in:** `agents/` inside a Plugin (see §6).

---

## 5. Workflows (Deterministic Multi-Agent Orchestration)

**Triggered by:** Claude using the `Workflow` tool (requires explicit user opt-in or "ultracode" mode).

**What they are:** JavaScript scripts that deterministically orchestrate multiple agents using:
- `agent(prompt, opts)` — spawn one agent
- `parallel(thunks)` — run agents concurrently (barrier: waits for all)
- `pipeline(items, ...stages)` — process items through stages with no unnecessary barrier
- `phase(title)` — group agents visually in the progress display

**When to use:** Tasks too large for one context window, or needing independent parallel perspectives (audit, migration, comprehensive review).

---

## 6. Plugins (Bundled Extensions)

**Location:** `~/.claude/plugins/`

**Install via:** `/plugin install <name>@<marketplace>` or `/plugin > Discover`

**Structure:**
```
plugin-name/
├── .claude-plugin/
│   └── plugin.json      ← required metadata
├── .mcp.json            ← optional MCP server config
├── commands/            ← slash commands (legacy format)
├── skills/              ← skill definitions (preferred)
├── agents/              ← reusable agent definitions
└── README.md
```

Plugins bundle commands, skills, agents, and MCP servers into one installable unit.

---

## 7. Memory System

**Location:** `~/.claude/projects/<project>/memory/`

| File | Purpose |
|---|---|
| `MEMORY.md` | Index — always loaded. One line per memory entry. |
| `user_*.md` | Who the user is, their role, expertise, preferences |
| `feedback_*.md` | How Claude should behave — corrections and confirmations |
| `project_*.md` | Current goals, decisions, deadlines |
| `reference_*.md` | Where to find things in external systems |

Memory files use frontmatter:
```yaml
---
name: feedback-no-summaries
description: User wants terse responses with no trailing summaries
metadata:
  type: feedback
---
Rule: ...
Why: ...
How to apply: ...
```

---

## 8. Settings & Permissions

**Files:** `.claude/settings.json` (project) · `~/.claude/settings.json` (user-global)

**Key fields:**
```json
{
  "permissions": {
    "allow": ["Bash(npm run *)", "Read", "Edit"],
    "deny": ["Bash(rm -rf *)"]
  },
  "hooks": {
    "PreToolUse": [{ "matcher": "Bash", "hooks": [{ "type": "command", "command": "echo pre" }] }],
    "PostToolUse": [...],
    "Stop": [...]
  },
  "env": {
    "MY_VAR": "value"
  }
}
```

Hooks run shell commands automatically around tool calls — use for linting, logging, notifications.

---

## 9. Decision Guide — Which Extension Point to Use?

| Goal | Use |
|---|---|
| Always-available project instructions | `CLAUDE.md` |
| Persistent facts across sessions | Memory system |
| User types `/foo` to trigger a task | Command or Skill with `argument-hint` |
| Claude activates automatically by context | Skill (model-invoked via `description`) |
| Parallel or isolated sub-tasks | Agent |
| Complex fan-out orchestration | Workflow |
| Reusable bundle for multiple projects | Plugin |
| Pre/post tool automation | Hook in `settings.json` |

---

## This Project's Extensions

| Type | Name | Purpose |
|---|---|---|
| Skill | `review-tests` | Auto-review Python automation tests against 14 QA best practices |