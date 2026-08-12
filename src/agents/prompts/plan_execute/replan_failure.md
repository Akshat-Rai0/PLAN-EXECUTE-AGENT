

Context of completed/failed steps:
{context_str}

Please revise/update the remaining steps of the plan based on the context above. Keep only pending and revised steps in the returned list of subtasks.

CRITICAL — read each failure reason carefully before writing new steps:
- If a step's error says a search "doesn't answer" or "doesn't specify" or "doesn't contain" the needed information, that means the search ran successfully but was too GENERIC or too BROAD. Do not repeat a similarly generic search — the new step's task description must be MORE SPECIFIC than the one that failed. Narrow it using any concrete details already surfaced in other steps' results (exact team/entity names, exact dates, tournament stage, match ID, etc.) rather than re-describing the same broad question in different words.
- Example: if "search for the latest match results" failed because the results were a generic schedule/fixture list with no explicit winner, the next step should target the SPECIFIC match already identified (e.g. "search for the result of the France vs Spain semi-final on July 14, 2026"), not a rephrased generic query like "find recent match results".
- If you cannot identify a more specific angle from the available context, say so explicitly in the step's task description (e.g. "no more specific match identified in prior results — broaden search to include result pages specifically, not schedule/fixture pages") rather than silently repeating the same query shape that already failed.

CRITICAL — if a failed step used tool_hint "start_server" (e.g. error mentions
"did not open port", "port never opened", or a dev-server startup failure):
- NEVER give the retry/diagnostic step tool_hint "shell_command". A dev server
  is a long-running process that never exits on its own — shell_command
  blocks until the underlying process exits, so pointing it at "npm run dev"
  or any other server-start command will hang indefinitely, not fail fast
  and not produce any diagnostic output. This is not a hypothetical: it has
  caused real hangs in this exact scenario.
- The ONLY correct tool_hint for starting or retrying a dev server is
  "start_server" — it already runs the process correctly (non-blocking,
  with a port-open timeout) and captures stderr/stdout output on failure
  for you to inspect in the step result. Re-use "start_server" again with
  the same or a corrected command; do not substitute shell_command.
- If the step's error already includes a "stderr:" section, that IS the
  diagnostic output — read it and write a fix (e.g. installing a missing
  dependency via shell_command, fixing a config file via write_file)
  BEFORE the next start_server attempt, rather than generating another
  step whose sole purpose is "run it again to see the error" — you may
  already have the error.

CRITICAL — if a failed step used tool_hint "shell_command" and the error
indicates the command was rejected, blocked, or not in the allowed command
list:
- Do NOT repeat the same command shape or the same shell wrapper on the next
    attempt.
- Rewrite the step to use an allowed command directly, or choose a different
    tool entirely (for file deletion and clearing, use delete_file instead of rm).
- Treat this as a command-shape problem, not as evidence that retrying the
    same shell step will suddenly succeed.

