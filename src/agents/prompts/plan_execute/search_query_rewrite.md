Overall User Goal: "{goal}"
Current Step Task: "{step_task}"
Prior Context / Findings: "{prior_context}"
Current Date / Anchor: "{current_date}"

Web Search Formulation Principles:
1. Classify & Strip Framing: Remove conversational framing, polite language, and instructions (e.g. "Step 1:", "Search for", "Find out", "Look up", "Google the", "Check if"). Focus purely on the underlying information need.
2. Disambiguate Entities: Resolve ambiguous pronouns, references, and relative terms ("it", "they", "the team", "the winner", "this company", "current model") into specific canonical names, entities, tournaments, or topics using the Overall Goal and Prior Context.
3. Enforce Freshness & Temporal Anchoring:
   - If the task requires time-sensitive, recent, or "latest" information, anchor the query with the exact year/month from the Current Date / Anchor (e.g. "2026", "August 2026").
   - For specific historical or dated events, use the exact date/year established in prior findings.
4. Target Authoritative Evidence:
   - Structure the query to surface primary sources (e.g., official announcements, product documentation, regulatory filings, research papers) or established reporting rather than generic forum chatter.
   - For technical or specific topics, include discriminating keywords (e.g., exact model names, version numbers, API endpoints, metrics).
5. Query Density & Length: Output a single, focused, keyword-dense query (typically 3 to 10 words) that search engines can match precisely against authoritative pages.

Output ONLY the raw search query:
