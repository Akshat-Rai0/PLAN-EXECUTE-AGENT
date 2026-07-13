# Plan-and-Execute Agent — 10 Worked Examples

Each example traces a real user goal through the full pipeline: **Planner → Executor → (Synthesizer / Browser / HITL as needed) → Replanner → Final Answer**. Use these as raw material for the golden dataset (tag each with its category a–e) and as demo scripts for the README/blog.

---

## 1. Fuel cost estimate (Delhi → Mumbai)

**Goal:** "How much petrol money to get from Delhi to Mumbai in a Swift Dzire?"

- **Plan:** get distance → get mileage → get current petrol price → compute cost
- **Executor:** distance and price come from **search** (price is time-sensitive, must be live); mileage from search too if the car model is specified, otherwise the planner should state a default assumption
- **Synthesis:** no fixed "fuel cost calculator" tool exists → executor routes to synthesizer → LLM writes `fuel_cost(distance_km, mileage_kmpl, price_per_litre)` → runs in the network-isolated code sandbox (pure arithmetic, no outbound calls needed) → validated against a numeric schema → registered as a reusable tool for future fuel-cost goals
- **HITL:** none — nothing irreversible
- **Replan:** only triggers if distance/price search returns ambiguous multi-route figures
- **Category:** (c) straightforward / (d) synthesis-required hybrid — good dual-purpose golden dataset goal

---

## 2. Cheapest flight booking

**Goal:** "Find and book the cheapest flight from NYC to SFO next Friday, under $300."

- **Plan:** search flight options → compare prices → select cheapest under budget → fill booking form → confirm
- **Executor:** search tool can surface options, but actual selection/booking requires the **browser tool** since most booking sites have no public API
- **Synthesis:** possibly a small `parse_price_table()` tool if the site's fare listing isn't cleanly scraped by generic browser extraction
- **HITL:** **mandatory** — the final booking/payment click is irreversible, gate pauses and shows the selected flight + price before submit
- **Prompt-injection note:** page content (fare listings, promo banners) is treated as data only — the agent must not "follow" any instruction-like text embedded in the page
- **Replan:** if no flight is under $300, replanner should surface that and ask whether to relax the budget rather than silently booking something else
- **Category:** (e) browser-only, also touches HITL

---

## 3. Nightly ETL pipeline failure diagnosis

**Goal:** "Our nightly ETL job failed last night — figure out why and fix it."

- **Plan:** read job logs → identify failure point → diagnose root cause → propose fix → apply fix → re-run
- **Executor:** step 1 (read logs) is a fixed file-I/O tool call
- **Replan trigger:** step 1 surfaces new information — e.g., the failure is a schema mismatch, not a timeout as initially assumed — replanner rewrites the remaining steps around the *actual* cause instead of a generic retry
- **Synthesis:** if the fix requires a one-off migration script not covered by any fixed tool, synthesizer generates it, validated against expected schema, sandboxed
- **HITL:** re-running against production data is irreversible-adjacent → gate before the "re-run" step, showing the diff/patch that will be applied
- **Category:** (a) forced replan — canonical example for this bucket

---

## 4. Competitive research report

**Goal:** "Research three competing approaches to vector databases and produce a comparison table."

- **Plan:** search approach A → search approach B → search approach C → synthesize table
- **Executor:** all four steps map cleanly to fixed tools (search + final synthesis, not tool-synthesis)
- **Synthesis:** none needed — "synthesize" here just means combining results into a final answer, not generating a new tool
- **HITL:** none
- **Replan:** none expected — this is the cleanest "no replanning" comparison point against ReAct for the ablation
- **Category:** (c) straightforward — this is your efficiency-savings showcase goal (fewest LLM calls vs. ReAct, since the structure never changes mid-run)

---

## 5. Weekly grocery reorder

**Goal:** "Reorder the groceries we usually buy and check out."

- **Plan:** check pantry-inventory tool (if wired in) or use last order history → build cart on retailer site → apply any saved coupons → checkout
- **Executor:** cart-building needs the **browser tool** (retailer site, no API)
- **HITL:** **mandatory** before checkout — this is a real payment, the textbook case for the approval gate
- **Synthesis:** possibly a small tool to diff "usual order" against "current cart" if no such fixed tool exists
- **Replan:** if an item is out of stock, replanner should insert a substitution step rather than failing the whole goal
- **Category:** (e) browser + irreversible action — best demo case for the HITL gate specifically

---

## 6. Legacy Flask → FastAPI route migration

**Goal:** "Convert this Flask app's routes to FastAPI syntax."

- **Plan:** read source files → identify all route definitions → convert syntax → write output files → run tests
- **Executor:** file I/O for read/write; no fixed tool does route-syntax conversion
- **Synthesis:** executor detects the gap → synthesizer writes an AST-based `convert_route_syntax()` function → sandbox-executed (filesystem-scratch only, no network needed) → output validated against expected FastAPI syntax schema → registered for reuse on future files in the same run
- **HITL:** writing to the actual source tree (not scratch) could be flagged sensitive — gate shows the diff before applying
- **Replan:** if tests fail after conversion, replanner routes back to a "fix conversion" step rather than declaring done
- **Category:** (d) synthesis-required — output correctness is the real test here (silent-wrong-output risk), so this is a good candidate for a strict schema-validation eval slice

---

## 7. Meeting prep dossier

**Goal:** "Pull everything relevant before my call with Acme Corp tomorrow."

- **Plan:** search recent Acme news → pull last email thread (if an email/MCP connector is wired in) → pull CRM notes → synthesize one-page brief
- **Executor:** mixes external search with internal-tool calls (Gmail/CRM via MCP) — this is the case that exercises tool priority: internal data sources should be preferred over web search once they're available
- **Synthesis:** none needed unless a custom internal data format needs a one-off parser
- **HITL:** none — informational output only, nothing irreversible
- **Replan:** if the internal connector isn't authorized/connected, replanner should degrade gracefully to search-only rather than failing the whole goal
- **Category:** (c) straightforward, useful for testing the "internal tool priority" pattern

---

## 8. Support ticket triage at volume

**Goal:** "Classify and route this incoming support ticket, draft a first response."

- **Plan:** classify ticket type/urgency → route to correct queue → draft response
- **Executor:** classification via LLM call against a fixed taxonomy tool; routing via an internal ticketing-system tool
- **Synthesis:** none typically — this is meant to be a fast, cheap, high-volume case
- **HITL:** none for classification/draft; would apply only if the agent were also empowered to *send* the response automatically (an irreversible external action) — worth deciding explicitly whether send is in scope
- **Replan:** only if classification confidence is low — replanner inserts an "ask a clarifying question to the customer" step
- **Category:** (c) — but the interesting metric here isn't correctness, it's **LLM-call cost at volume**, since Plan-and-Execute's efficiency win compounds when you run this thousands of times a day

---

## 9. Contract compliance check

**Goal:** "Does this vendor contract violate our standard terms?"

- **Plan:** extract clauses from the uploaded contract → compare against standard-terms reference doc → flag deviations → summarize risk
- **Executor:** file-parsing tool (PDF/doc) + a comparison step, likely LLM-driven rather than tool-driven
- **Synthesis:** possibly a structured clause-extraction tool if the fixed file-parsing tool doesn't already return clause-level structure
- **HITL:** none — output is advisory, no action is taken on the agent's behalf
- **Replan:** none expected — this is a good "no replanning, high-stakes accuracy" case; worth a stricter judge-scoring bar than the other examples since a wrong "no violation" answer here has real consequences even without an irreversible action being taken
- **Category:** (c), but flagged for extra judge scrutiny given the stakes of the domain

---

## 10. Flight/train price watch across a date range

**Goal:** "Check train prices from Delhi to Mumbai for every day next week and tell me the cheapest day to travel."

- **Plan:** for each of 7 days, look up ticket price → collect results → identify minimum → report
- **Executor:** no fixed tool likely covers "IRCTC-style price-by-date lookup" — this either needs the **browser tool** (if the railway site has no API) or a synthesized scraper/tool if there's a semi-structured page to parse
- **Synthesis:** if browser scraping returns raw HTML/text, a synthesized `parse_fare_table()` tool structures it into comparable numbers, validated against a numeric schema before being trusted
- **HITL:** none for the lookup itself; would apply if the goal extended to "and book the cheapest one"
- **Replan:** if a given day's page fails to load or the site rate-limits repeated lookups, that step goes FAILED → replanner decides whether to retry with backoff or skip that day and report partial results
- **Category:** (e) likely browser-required, also touches multi-step loop handling (7 near-identical sub-lookups) — good stress test for whether the planner over-generates near-duplicate steps efficiently or bloats the plan

---

## Summary table

| # | Goal | Primary category | Key capability exercised |
|---|---|---|---|
| 1 | Fuel cost estimate | c/d | Tool synthesis (arithmetic) |
| 2 | Cheapest flight booking | e | Browser + HITL |
| 3 | ETL failure diagnosis | a | Forced replan |
| 4 | Competitive research report | c | Planning efficiency (no replan) |
| 5 | Grocery reorder | e | HITL (payment) |
| 6 | Flask → FastAPI migration | d | Tool synthesis (codegen) |
| 7 | Meeting prep dossier | c | Internal tool priority |
| 8 | Support ticket triage | c | Cost-at-volume |
| 9 | Contract compliance check | c | High-stakes accuracy, no action |
| 10 | Multi-day price watch | e | Browser + loop/plan-size handling |

These ten collectively cover all five golden-dataset categories (a–e) from the spec, plus the HITL and internal-tool-priority patterns that the original 20-goal dataset description didn't call out explicitly — worth folding a couple of these directly into the actual golden dataset rather than writing new ones from scratch.