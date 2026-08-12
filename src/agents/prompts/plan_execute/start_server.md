You are determining how to start the dev server for a software project.

Overall goal: "{plan.goal}"
Project workspace directory: {workspace_path}

Step to complete: {current_step.task}

Prior steps and results:
{context_block}

Output a JSON object with exactly two keys:
  "command": the server start command string (e.g. "npm run dev", "python3 -m http.server 3000")
  "port": the integer port number the server will listen on

Common conventions:
- Vite (React/Vue): command="npm run dev", port=5173
- Create React App: command="npm start", port=3000
- Next.js: command="npm run dev", port=3000
- Flask: command="python3 app.py", port=5000
- Express: command="node index.js", port=3000
- Python http.server: command="python3 -m http.server 8080", port=8080

No markdown fences — output only the raw JSON object.
