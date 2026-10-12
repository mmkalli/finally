---
description: Interactive menu to list, create, edit, delete and run subagents
argument-hint: "[list|create|edit|delete|run]"
---

You are running an interactive subagent manager, a replacement for the old `/agents` wizard. Talk to the user in English. Use the AskUserQuestion tool for every choice so the user gets a selectable menu, not free-text prompts.

Subagents are Markdown files with YAML frontmatter:
- Project agents: `.claude/agents/<name>.md` (relative to the project root)
- User agents (all projects): `~/.claude/agents/<name>.md`

File format:

```markdown
---
name: <kebab-case-name>
description: <when Claude should use this agent>
tools: <optional comma-separated list, e.g. Read, Grep, Glob, Edit, Write, Bash; omit to inherit all tools>
model: <optional: sonnet | opus | haiku | inherit; omit to inherit>
---

<system prompt: the agent's role and instructions>
```

## Step 1: Show the current agents

Read both agent folders (a missing folder just means no agents there). Print a short table: name, scope (project/user), description.

## Step 2: Main menu

If `$ARGUMENTS` names an action, skip straight to it. Otherwise ask with AskUserQuestion (header "Agents"):
- **Create new agent**
- **Edit an agent**
- **Delete an agent**
- **Run an agent**

## Create new agent

1. Ask for scope: **Project** (`.claude/agents/`, recommended) or **User** (`~/.claude/agents/`).
2. Ask how to build it: **Generate with Claude** (recommended: the user describes what the agent should do and you draft the name, description and system prompt) or **Manual** (the user supplies each field).
3. Ask which tools it gets (multiSelect): **All tools (inherit)**, **Read-only (Read, Grep, Glob)**, **Edit files (Read, Edit, Write, Grep, Glob)**, **Shell (Bash)**.
4. Ask for the model: **Inherit (Recommended)**, **Sonnet**, **Opus**, **Haiku**.
5. Collect any free-text details by asking the user in a normal message and waiting for the reply.
6. Show the full file content as a preview, then ask **Save**, **Change something** or **Cancel**.
7. If they pick Save, write the file. Refuse to overwrite an existing agent with the same name unless the user confirms.

## Edit an agent

Ask which agent (one option per agent; if there are more than 4, ask for the name in a message). Show its current content, ask which part to change (**Description**, **Tools**, **Model**, **System prompt**), apply the change, show a preview and confirm before saving.

## Delete an agent

Ask which agent, show its content, and ask for confirmation (**Delete** / **Cancel**) before removing the file.

## Run an agent

Ask which agent, then ask the user in a message what task to give it. Launch it with the Agent tool, setting `subagent_type` to the agent's name, and report its result. A newly created agent may only be available after Claude Code restarts. If launching it fails for that reason, tell the user so.

## Finish

After an action completes, ask whether to **Return to menu** or **Exit**.
