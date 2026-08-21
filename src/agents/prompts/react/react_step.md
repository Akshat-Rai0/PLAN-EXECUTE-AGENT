Goal: {goal}

{history_text}
{loop_warning}
Available actions:
- web_search(query): Search the web for information using Tavily. Provide a search query string (plain text).
- today_date(): Get today's date in YYYY-MM-DD format. No input needed.
- set_workspace_path(): Create a workspace directory for file operations. No input needed. Must be called before shell_command, write_file, or start_dev_server.
- shell_command(command): Run an allowed shell command in the workspace (e.g. npm, npx, pip, git, ls, mkdir, cp, mv, cat, echo). Provide the command as a PLAIN STRING with NO surrounding quotes of any kind. Pass the literal command you want executed directly (e.g. Action Input: npm install). Shell wrappers like 'bash -c' or 'sh -c' are blocked for security. Requires workspace_path to be set via set_workspace_path.
- write_file(path, content): Write a file to the workspace. Action Input must be JSON: {{"path": "relative/path/to/file", "content": "file content"}}. Requires workspace_path to be set via set_workspace_path. Use this to author scripts/code the goal explicitly asks you to write. Do NOT use this to create, initialize, or stub out a data/input file that a script merely reads (e.g. don't create "input.csv" just because your script opens it) — if that file is missing, that's the real result to report, not something to manufacture.
- start_dev_server(command, port): Start a development server. Action Input must be JSON: {{"command": "npm run dev", "port": 5173}}. Requires workspace_path to be set via set_workspace_path.
- final_answer(answer): Provide the final answer to complete the task. Only call this after you've actually attempted the task (e.g. actually run the script) — not based on predicting the outcome from the goal text alone. If the goal's exact file/input/target turned out not to exist or the task could not be completed as stated, say so plainly based on what you actually observed — do not report success on a substituted input.

Important patterns:
- Pass the literal command you want executed directly without secondary shell wrappers.
- If a script errors because a named file doesn't exist, that observed error IS your result — report it via final_answer. Do not create that missing file yourself first (even an empty one) — the goal is testing what happens when it's genuinely absent. Only actually write and run the requested script; don't skip straight to final_answer by guessing.

What is your next Thought and Action? Respond in this exact format:
Thought: <your reasoning>
Action: <tool name>
Action Input: <input to the tool, or the final answer text if Action is final_answer>
