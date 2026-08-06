Overall User Goal: "{goal}"
Current Step Task: "{step_task}"
Prior Context / Findings: "{prior_context}"
Current Date / Anchor: "{current_date}"

Instructions:
1. Strip all conversational framing, instructions, and prompt artifacts (e.g. "Step 1:", "Search for", "Find out", "Look up", "Google the", "Check if").
2. Resolve ambiguous pronouns and references ("it", "they", "the team", "the winner", "this company", "current", "latest") into specific named entities, years, and events using the Overall Goal and Prior Context.
3. If temporal references exist ("latest", "this year", "current"), anchor them using the Current Date / Anchor if appropriate.
4. Output a single, focused, keyword-rich search query (typically 3 to 10 words) that search engines can answer precisely.

Output ONLY the raw search query:
