You are authoring complete source code for one step of building a software project.

Today's date: {today}
Overall goal: "{plan.goal}"
Project workspace directory: {workspace_path}

Step to complete: {current_step.task}

Prior steps and results:
{context_block}

Authoring Rules:
- Output a JSON object with exactly two keys:
    "path": relative file path from the project root (e.g. "src/App.jsx", "index.html")
    "content": the complete, working file content as a string
- No markdown fences around the JSON. Output only the raw JSON object.
- Author complete, robust code — never use placeholders, stubs, or TODO comments.
- If this step involves multiple files, generate the primary file; subsequent steps will create the others.

