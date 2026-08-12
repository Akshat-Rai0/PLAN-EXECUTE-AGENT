You are given the results of executing a multi-step plan toward this goal: "{plan.goal}"

For information/research goals: extract the specific facts that answer the goal, ignoring boilerplate.
For app-building goals: summarize what was built, what files were created, and — most importantly — how to access the running app.

Step results:
{chr(10).join(step_results)}

{f"\n✅ A dev server is running at: {state.get('server_url')}\n" if state.get('server_url') else ''}

Provide a clear, direct final answer. For apps, lead with the URL if one is running.
If any step result starts with "[UNVERIFIED:", you must explicitly mention in your final answer that you could not confirm that specific piece of information. Do NOT state unverified facts as true or confidently.
