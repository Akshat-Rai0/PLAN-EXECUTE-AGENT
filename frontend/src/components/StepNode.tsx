import { useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ChevronDown,
  Globe,
  Map,
  RefreshCw,
  Sparkles,
  Wrench,
  Brain,
  AlertTriangle,
} from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type { RunStepEvent, StepType } from '../lib/types'
import { armTheme } from '../lib/armTheme'
import { latencyMs } from '../lib/types'
import { springStep } from '../lib/motion'
import { useReducedMotion } from '../hooks/useAccessibility'
import { BrowserFilmstrip } from './BrowserFilmstrip'

const TYPE_ICONS: Record<StepType, typeof Map> = {
  plan: Map,
  tool_call: Wrench,
  tool_result: Wrench,
  reflection: Brain,
  replan: RefreshCw,
  browser_step: Globe,
  synthesis: Sparkles,
  interrupt: AlertTriangle,
}

interface StepNodeProps {
  step: RunStepEvent
  selected: boolean
  onSelect: (stepId: string) => void
  isBranch?: boolean
  highlighted?: boolean
}

function JsonBlock({ label, data }: { label: string; data: unknown }) {
  const [open, setOpen] = useState(true)
  const text = useMemo(() => {
    try {
      return typeof data === 'string' ? data : JSON.stringify(data, null, 2)
    } catch {
      return String(data)
    }
  }, [data])

  if (data == null || (typeof data === 'object' && Object.keys(data as object).length === 0)) return null

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="font-sans text-[10px] uppercase tracking-wide text-white/45 transition "
      >
        {open ? '▼' : '▶'} {label}
      </button>
      {open && (
        <div className="mt-1 overflow-x-auto rounded border border-white/[0.06] text-xs">
          <SyntaxHighlighter
            language="json"
            style={oneDark}
            customStyle={{ margin: 0, padding: '8px 10px', background: 'rgba(0,0,0,0.35)', fontSize: '11px' }}
          >
            {text}
          </SyntaxHighlighter>
        </div>
      )}
    </div>
  )
}

export function StepNode({ step, selected, onSelect, isBranch, highlighted }: StepNodeProps) {
  const [expanded, setExpanded] = useState(false)
  const reducedMotion = useReducedMotion()
  const theme = armTheme(step.arm)
  const Icon = TYPE_ICONS[step.type] ?? Wrench
  const ms = latencyMs(step)
  const isRunning = step.status === 'running'
  const isFailed = step.status === 'failed'

  const borderColor = isFailed ? '#f87171' : isRunning ? theme.color : 'rgba(255,255,255,0.08)'

  return (
    <div className="relative pl-6">
      <div
        className="absolute left-[9px] top-0 bottom-0 w-px"
        style={{
          background: isBranch
            ? `repeating-linear-gradient(to bottom, ${theme.color}88 0, ${theme.color}88 4px, transparent 4px, transparent 8px)`
            : 'rgba(255,255,255,0.08)',
        }}
      />
      <div className="absolute left-[5px] top-4 h-2 w-2 rounded-full" style={{ background: theme.color }} />

      <motion.article
        layout
        className="mb-3 rounded-lg border border-white/[0.06] bg-white/[0.02]"
        style={{
          borderLeftWidth: 3,
          borderLeftColor: borderColor,
          boxShadow: isRunning ? `0 0 12px ${theme.glow}` : highlighted ? `0 0 8px ${theme.glow}` : undefined,
        }}
      >
        <button
          type="button"
          onClick={() => {
            onSelect(step.step_id)
            setExpanded((e) => !e)
          }}
          className="flex w-full items-center gap-2 px-3 py-2.5 text-left transition "
          style={{ background: selected ? 'rgba(255,255,255,0.03)' : undefined }}
        >
          <Icon size={14} style={{ color: theme.color }} />
          <div className="min-w-0 flex-1">
            <p className="truncate font-sans text-xs text-white/85">{step.title}</p>
            <p className="font-mono text-[10px] uppercase tracking-wide text-white/35">{step.type}</p>
          </div>
          {isRunning ? (
            <motion.span
              className="rounded px-1.5 py-0.5 font-mono text-[10px]"
              style={{ color: theme.color, border: `1px solid ${theme.border}` }}
              animate={reducedMotion ? {} : { opacity: [1, 0.45, 1] }}
              transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
            >
              running
            </motion.span>
          ) : ms != null ? (
            <span className="font-mono text-[10px] text-white/40">{ms}ms</span>
          ) : null}
          <ChevronDown
            size={14}
            className="text-white/35 transition-transform"
            style={{ transform: expanded ? 'rotate(180deg)' : undefined }}
          />
        </button>

        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div
              key="detail"
              initial={reducedMotion ? { opacity: 0 } : { height: 0, opacity: 0 }}
              animate={reducedMotion ? { opacity: 1 } : { height: 'auto', opacity: 1 }}
              exit={reducedMotion ? { opacity: 0 } : { height: 0, opacity: 0 }}
              transition={springStep(reducedMotion)}
              className="overflow-hidden border-t border-white/[0.06] px-3 pb-3"
            >
              {isFailed && step.payload.error && (
                <p className="mt-2 rounded border border-red-500/30 bg-red-500/10 px-2 py-1 font-mono text-[11px] text-red-300">
                  {step.payload.error}
                </p>
              )}
              <JsonBlock label="args" data={step.payload.args} />
              <JsonBlock label="result" data={step.payload.result} />
              {step.type === 'synthesis' && step.payload.result != null && (
                <div className="mt-2 rounded border border-amber-500/20 bg-amber-500/5 p-2">
                  <p className="font-sans text-[10px] uppercase text-amber-300/80">Generated code</p>
                  <pre className="mt-1 overflow-x-auto font-mono text-[11px] leading-relaxed text-amber-100/90">
                    {typeof step.payload.result === 'string'
                      ? step.payload.result
                      : typeof step.payload.result === 'object' && 'source_code' in (step.payload.result as object)
                        ? String((step.payload.result as { source_code?: unknown }).source_code ?? '')
                        : JSON.stringify(step.payload.result, null, 2)}
                  </pre>
                </div>
              )}
              {step.type === 'browser_step' && step.payload.screenshot_url && (
                <BrowserFilmstrip screenshotUrl={step.payload.screenshot_url} title={step.title} />
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.article>
    </div>
  )
}
