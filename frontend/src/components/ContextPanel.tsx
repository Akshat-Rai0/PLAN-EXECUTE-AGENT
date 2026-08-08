import { motion } from 'framer-motion'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { RunStepEvent, RunSummary } from '../lib/types'
import { armTheme } from '../lib/armTheme'
import { totalTokens, latencyMs } from '../lib/types'
import { springPanel } from '../lib/motion'
import { useReducedMotion, useReducedTransparency } from '../hooks/useAccessibility'

interface ContextPanelProps {
  run: RunSummary | null
  steps: RunStepEvent[]
  selectedStep: RunStepEvent | null
  previewStep: RunStepEvent | null
  collapsed: boolean
  onToggleCollapse: () => void
}

export function ContextPanel({
  run,
  steps,
  selectedStep,
  previewStep,
  collapsed,
  onToggleCollapse,
}: ContextPanelProps) {
  const reducedMotion = useReducedMotion()
  const reducedTransparency = useReducedTransparency()
  const panelBg = reducedTransparency ? 'rgba(17,17,20,0.95)' : 'rgba(17,17,20,0.75)'

  const displayStep = selectedStep ?? previewStep
  const isPreview = !selectedStep && !!previewStep

  const tokens = totalTokens(steps)
  const totalLatency = steps.reduce((acc, s) => acc + (latencyMs(s) ?? 0), 0)
  const retryCount = steps.filter((s) => s.type === 'replan').length

  return (
    <motion.aside
      className="flex h-full flex-col border-l border-white/[0.06] border-t border-t-white/[0.06]"
      style={{
        background: panelBg,
        backdropFilter: reducedTransparency ? undefined : 'blur(20px)',
      }}
      animate={{ width: collapsed ? 48 : 320 }}
      transition={springPanel(reducedMotion)}
    >
      <div className="flex items-center justify-between border-b border-white/[0.06] px-3 py-3">
        <button
          type="button"
          onClick={onToggleCollapse}
          className="rounded p-1 text-white/50 transition hover:bg-white/5 hover:text-white/80 active:scale-95 focus-visible:outline focus-visible:outline-1 focus-visible:outline-white/30"
        >
          {collapsed ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
        {!collapsed && <h2 className="font-sans text-sm font-semibold tracking-tight text-white/90">Context</h2>}
      </div>

      {!collapsed && (
        <div className="flex-1 overflow-y-auto p-4">
          {!run ? (
            <p className="font-sans text-xs text-white/40">No run selected</p>
          ) : displayStep ? (
            <motion.div
              key={displayStep.step_id}
              initial={reducedMotion ? { opacity: 0 } : { opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: reducedMotion ? 0.01 : 0.15 }}
            >
              {isPreview && (
                <p className="mb-2 font-sans text-[10px] uppercase tracking-wide text-white/35">
                  Preview — click step to pin
                </p>
              )}
              <StepDetail step={displayStep} retryCount={retryCount} />
            </motion.div>
          ) : (
            <RunSummaryPanel run={run} stepCount={steps.length} tokens={tokens} totalLatency={totalLatency} />
          )}
        </div>
      )}
    </motion.aside>
  )
}

function RunSummaryPanel({
  run,
  stepCount,
  tokens,
  totalLatency,
}: {
  run: RunSummary
  stepCount: number
  tokens: { input: number; output: number }
  totalLatency: number
}) {
  const theme = armTheme(run.arm)
  return (
    <div className="space-y-4">
      <div>
        <p className="font-sans text-[10px] uppercase tracking-wide text-white/40">Run summary</p>
        <h3 className="mt-1 font-sans text-base font-semibold tracking-tight text-white/90">{run.task_name}</h3>
      </div>
      <span
        className="inline-block rounded px-2 py-0.5 font-sans text-xs"
        style={{ color: theme.color, background: theme.bg, border: `1px solid ${theme.border}` }}
      >
        {theme.label}
      </span>
      <dl className="space-y-2 font-mono text-xs text-white/60">
        <div className="flex justify-between"><dt>Steps</dt><dd>{stepCount}</dd></div>
        <div className="flex justify-between"><dt>Tokens in</dt><dd>{tokens.input}</dd></div>
        <div className="flex justify-between"><dt>Tokens out</dt><dd>{tokens.output}</dd></div>
        <div className="flex justify-between"><dt>Latency</dt><dd>{(totalLatency / 1000).toFixed(2)}s</dd></div>
        <div className="flex justify-between"><dt>Outcome</dt><dd>{run.pass_fail == null ? '—' : run.pass_fail ? 'PASS' : 'FAIL'}</dd></div>
      </dl>
    </div>
  )
}

function StepDetail({ step, retryCount }: { step: RunStepEvent; retryCount: number }) {
  const theme = armTheme(step.arm)
  return (
    <div className="space-y-3">
      <div>
        <p className="font-sans text-[10px] uppercase tracking-wide text-white/40">Step detail</p>
        <h3 className="mt-1 font-sans text-sm font-medium text-white/90">{step.title}</h3>
      </div>
      <dl className="space-y-2 font-mono text-[11px] text-white/55">
        <div><dt className="text-white/35">step_id</dt><dd className="break-all">{step.step_id}</dd></div>
        <div><dt className="text-white/35">type</dt><dd>{step.type}</dd></div>
        <div><dt className="text-white/35">status</dt><dd style={{ color: theme.color }}>{step.status}</dd></div>
        {step.payload.model && <div><dt className="text-white/35">model</dt><dd>{step.payload.model}</dd></div>}
        {step.payload.tool_name && <div><dt className="text-white/35">tool</dt><dd>{step.payload.tool_name}</dd></div>}
        <div><dt className="text-white/35">retries (run)</dt><dd>{retryCount}</dd></div>
        <div><dt className="text-white/35">tokens</dt><dd>{step.payload.tokens?.input ?? 0} in / {step.payload.tokens?.output ?? 0} out</dd></div>
      </dl>
      <pre className="max-h-64 overflow-auto rounded border border-white/[0.06] bg-black/30 p-2 font-mono text-[10px] leading-relaxed text-white/70">
        {JSON.stringify(step.payload, null, 2)}
      </pre>
    </div>
  )
}
