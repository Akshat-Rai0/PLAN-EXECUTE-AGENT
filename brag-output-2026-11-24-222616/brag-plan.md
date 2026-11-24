# Brag Plan: Plan-and-Execute Agent

## What is this app?
A LangGraph agent (FastAPI + React) that thinks before it acts: it decomposes a goal into ordered steps, executes each with the right tool — pausing for human approval on anything risky — replans when reality disagrees with the plan, and can even synthesize new tools it doesn't have, benchmarked against a plain ReAct baseline.

## The angle
The site already has the perfect deadpan headline: **"ReAct guesses. This plans."** The video takes that literally — open on the accusation against the baseline, then let the product answer with total calm. The joke is restraint: an agent that pauses to ask permission, rewrites its own plan when surprised, and treats "rm" as a forbidden word. Played completely straight.

## Hook (first 2-3 seconds)
Paper-white frame, lots of empty space. One serif line fades in, unhurried: **"ReAct guesses."** Nothing else. A small mono caption underneath: `baseline · no plan, no map`. The stillness is the hook — viewers lean in because the frame is quiet.

## Key moments (the middle)
- **The loop, made visible**: the product's own five-node cycle — `plan → execute → approval gate → check → synthesize` — rendered as the site's numbered-circle loop diagram, nodes lighting up in sequence.
- **The working app**: a recreated chat/debugger moment — a goal gets typed ("Who won the latest F1 race?"), the plan appears as ordered steps, a high-risk action triggers a literal **HITL approval gate** that pauses, then the run resumes and replans once when a step surprises it.
- **The receipts**: `19+ LangGraph nodes · 12 tools · 28 golden goals · 136 tests` as a quiet stat row — the site's own numbers.

## Outro / punchline
The product name lands slowly in serif: **Plan-and-Execute Agent**. Below it, the site's tagline in italic: *"Think first, then act."* Long hold on mostly-empty frame. One small mono line: `open source · langgraph · fastapi · react`. No confetti, no CTA button energy — it ends like the site does.

## User flow worth showing
Real flow from the product: user types a goal in chat → `plan_node` decomposes it into typed steps → `executor_node` routes low-risk tools directly while high-risk tools (shell, file writes, browser) hit the **approval_node** interrupt → `check_new_info_node` evaluates outcomes and can trigger a bounded replan → `synthesize_node` delivers the final answer. Show this as the centerpiece: typing → plan steps appearing → the approval gate pausing → resume → final answer. (The site also ships `agent_history.gif`, a real run trace — if Hyperframes can embed it cleanly, use it as a texture layer inside the chat scene; otherwise the recreated UI carries it.)

## Tone
- Preset: `deadpan`
- Creative direction: "editorial infra-project film — serif headlines, mono labels, long holds, one dry joke"
- Interpretation: 3-4 scenes with long settled holds; text enters slowly and stays; one idea per frame; music is a low bed that barely registers; SFX nearly absent — one dry hit at most.

## Format: landscape — 1920x1080
## Duration: ~20 seconds

## Visual identity (from the project)
- Background (hero): `#1a1917` ink; page paper: `#fbfaf6`; surface: `#f8f6f0`
- Accent: `#2b5f8a` blue (links/primary), `#c84b2f` rust (contrast italic), `#2a6b45` green (success/gates approved), `#9a5c0a` amber (gates/attention)
- Text on paper: `#1a1917` ink, secondary `#4a4843`, muted `#8a8880`
- Display font: **Fraunces** (serif, light weight, italic accents — the site's headline voice)
- Body/label font: **DM Sans**; mono labels: **DM Mono** (uppercase, letter-spaced — the site's section-label style)
- Strongest visual element: the hero's serif headline "An agent that *thinks first,* then acts." and the five numbered loop steps with colored number circles (ink, blue, amber, green, purple)

## Share copy (draft)
ReAct guesses. This plans. — an open-source plan-and-execute agent with human approval gates, a sandboxed runtime, and 136 tests. Think first, then act.

## Audio direction
- Role: sparse professional accents over a barely-there bed — deadpan restraint
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (steady, clean, 110 BPM — the preset's deadpan pick) at low volume (0.12-0.18), fading in gently and out at the end
- Music treatment: start ~0.5s in at low level, hold steady, fade out over the final 1.5s; it should feel like room tone with a pulse, not a soundtrack
- Music cue guidance: preset read — vol-12 @ ~110 BPM. Strong cues in window: 8.74s, 13.11s, 17.47s, 18.56s, 22.93s. Use at most 1-2: optionally let the plan-steps sequence breathe near a beat around 8.74-9.29s and save any final emphasis near 17.47-18.56s for the name card. Restraint rule: cues are optional; readability and the long holds win every time.
- Audio-reactive treatment: none — deadpan stays still
- SFX posture: very sparse — at most 2-3 dry cues: a soft `interface/drop_001`-class tick when the plan step appears, one quiet click on the approval gate, one soft bell (`impactBell_heavy_000` at low volume) under the final name card. Everything else silent.
- Audio-coupled moments: the approval gate interrupt is the one moment worth a sound — a muted, slightly serious click; the typing of the goal gets no keystrokes (deadpan doesn't foley)
- Restraint rule: no risers, no whooshes, no celebration stingers; if a cue would be "fun," cut it

## Storyboard

### Scene 1 — The accusation — 4.0s
Paper background (`#fbfaf6`), generous negative space. Centered serif line fades/rises slowly: **"ReAct guesses."** in Fraunces light. Below it, small DM Mono uppercase caption: `BASELINE · NO PLAN · NO MAP`. Nothing moves after the entrance — the hold is the joke setup.
Sequential/interaction: none
Audio intent: near-silence; the music bed is barely there, establishing "this video is calm"
Audio-coupled idea: none — no typing foley; the stillness is intentional
Music: vol-12 at ~0.14 volume, fading in
Transition mood: slow crossfade (0.8s) → Scene 2

### Scene 2 — The answer — 5.5s
Same paper field. Second serif line enters with a slow crossfade: **"This plans."** — slightly larger, with "plans" in italic accent blue. To the right or below, the product card materializes like the site's hero: dark ink (`#1a1917`) rounded card containing mono label `PLAN-AND-EXECUTE AGENT` and the site's own sub-line feel: "decomposes the goal, executes deliberately, replans when surprised." A thin rule and the hero-pill style tags (`HITL GATES`, `SANDBOXED`, `DYNAMIC TOOLS`) sit quietly under it.
Sequential/interaction: yes — the ink card and its pills arrive one by one, ~0.6s apart, then everything holds
Audio intent: the first small lift; one soft drop sound as the card lands
Audio-coupled idea: card entrance gets a single soft `interface/drop`-class tick; pills need no sound
Music: vol-12 continues
Transition mood: slow crossfade → Scene 3

### Scene 3 — The working agent — 7.0s (centerpiece)
Recreated product UI on the paper background, styled like the site's chat/debugger: a narrow chat panel on the left showing a user goal being typed: `who won the latest f1 race?` — then beneath it, plan steps materialize as a vertical list with mono node names appearing sequentially: `plan_node` → `tavily_search_node` → `reason_node` → `check_new_info_node` → `synthesize_node`, each with a small colored status dot (green done, amber running). Mid-sequence, one step (`shell_node` or `browser_use_node`) pauses behind an amber **APPROVAL GATE** chip reading `human approval required — high risk`; a beat of stillness, then it flips to approved and the sequence resumes. A novelty tick on `check_new_info_node` fires once — "replan" appears briefly in amber — before `synthesize_node` delivers a short final-answer block.
Sequential/interaction: yes — goal types in (or fades), five plan steps appear one by one with status changes, the approval gate interrupts and resolves, one replan tick fires; all readable holds between beats
Audio intent: the only scene with interior sound — dry, procedural, like watching a machine work
Audio-coupled idea: approval gate gets one muted serious click; the replan tick gets a very quiet tick; no typing foley; each step arrival is silent or near-silent
Music: vol-12 continues at same low level
Transition mood: slow crossfade → Scene 4

### Scene 4 — Receipts — 4.5s
Return to clean paper. The site's stat row arrives as quiet serif numerals with mono labels, staggered gently: `19+ LangGraph nodes` · `12 tools` · `28 golden goals` · `136 tests`. Then the name card: **Plan-and-Execute Agent** in Fraunces, italic subtitle *"Think first, then act."* Small mono footer: `OPEN SOURCE · LANGGRAPH · FASTAPI · REACT`. Long hold to end.
Sequential/interaction: yes — four stat pairs arrive one by one (~0.7s apart), then the name card settles; full set holds for the final ~2s
Audio intent: resolve; one soft bell under the name card, then the bed fades
Audio-coupled idea: name card entrance may sit near the vol-12 strong cue ~17.5s if it lands cleanly; otherwise free
Music: vol-12 fades out over final 1.5s
Transition mood: none — final hold

**Music mood for this video:** deadpan — low, steady, nearly subliminal
**Audio summary:** A barely-there 110 BPM bed carries four quiet scenes; sound exists only as two or three dry procedural ticks (gate click, one soft reveal bell), letting the stillness do the comedy.
