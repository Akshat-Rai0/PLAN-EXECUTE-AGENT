export type ArmName = 'react' | 'plan_execute' | 'plan_execute_synthesis'

export type StepType =
  | 'plan'
  | 'tool_call'
  | 'tool_result'
  | 'reflection'
  | 'replan'
  | 'browser_step'
  | 'synthesis'
  | 'interrupt'

export type StepStatus = 'running' | 'success' | 'failed' | 'waiting_for_input'
export type RunStatus = 'running' | 'success' | 'failed' | 'waiting_for_input'

export interface TokenUsage {
  input: number
  output: number
}

export interface StepPayload {
  args?: Record<string, unknown>
  result?: unknown
  tool_name?: string | null
  model?: string | null
  tokens?: TokenUsage
  error?: string | null
  screenshot_url?: string | null
}

export interface RunStepEvent {
  run_id: string
  step_id: string
  parent_step_id: string | null
  arm: ArmName
  type: StepType
  status: StepStatus
  title: string
  started_at: string
  ended_at: string | null
  payload: StepPayload
}

export interface RunSummary {
  run_id: string
  arm: ArmName
  task_name: string
  status: RunStatus
  duration_ms: number | null
  started_at: string
  pass_fail: boolean | null
}

export interface RunDetail extends RunSummary {
  ended_at?: string | null
  steps: RunStepEvent[]
}

export interface ChatMessage {
  run_id: string
  message_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
}

export interface InterruptResponse {
  decision?: 'approve' | 'reject' | 'alternative'
  alternative_input?: string
  human_response?: string
}

export interface NormalizedSteps {
  byId: Record<string, RunStepEvent>
  order: string[]
}

export function normalizeSteps(steps: RunStepEvent[]): NormalizedSteps {
  const byId: Record<string, RunStepEvent> = {}
  const order: string[] = []
  for (const step of [...steps].sort((a, b) => a.started_at.localeCompare(b.started_at))) {
    byId[step.step_id] = step
    if (!order.includes(step.step_id)) order.push(step.step_id)
  }
  return { byId, order }
}

export function mergeStep(existing: RunStepEvent | undefined, incoming: RunStepEvent): RunStepEvent {
  if (!existing) return incoming
  return { ...existing, ...incoming, payload: { ...existing.payload, ...incoming.payload } }
}

export function latencyMs(step: RunStepEvent): number | null {
  if (!step.ended_at) return null
  return new Date(step.ended_at).getTime() - new Date(step.started_at).getTime()
}

export function totalTokens(steps: RunStepEvent[]): TokenUsage {
  return steps.reduce(
    (acc, s) => ({
      input: acc.input + (s.payload.tokens?.input ?? 0),
      output: acc.output + (s.payload.tokens?.output ?? 0),
    }),
    { input: 0, output: 0 },
  )
}
