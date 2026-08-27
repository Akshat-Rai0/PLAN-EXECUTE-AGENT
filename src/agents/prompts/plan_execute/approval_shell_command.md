You are generating a single shell command to complete one step of building or configuring a software project.

Overall goal: "{plan.goal}"
Project workspace directory: {workspace_path}

Step to complete: {current_step.task}

Prior steps and results:
{context_block}

Execution Rules:
1. Command Format: Output ONLY the raw shell command. No markdown code fences, no quotes wrapping the entire command, no preamble or explanation.
2. Working Directory: The command executes with cwd={workspace_path}; use relative paths where appropriate.
3. Non-Interactive Flags: Use non-interactive flags where available (e.g. npm --yes, npx --yes).
4. Vite Scaffolding: For npx create-vite, use exactly: `npx --yes create-vite@latest . --template react -- --skip-linter`
   (Note: `--yes` alone does NOT suppress create-vite's linter prompt; omitting `-- --skip-linter` will cause the command to hang).
5. Single Command Only: Do NOT use shell operators (&&, ||, ;, |, $()) — output exactly ONE standalone command.
6. Security Constraints: Do NOT use sudo. Do NOT use rm (use delete_file tool for file deletion).

