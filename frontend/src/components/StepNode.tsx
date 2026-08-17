import { useMemo, useState, useEffect } from 'react'
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
  Check,
} from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type { RunStepEvent, StepType } from '../lib/types'
import { armTheme } from '../lib/armTheme'
import { latencyMs } from '../lib/types'
import { springStep, springEnter } from '../lib/motion'
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
  run_complete: Check,  // sentinel — filtered from UI, icon never rendered
}

interface StepNodeProps {
  step: RunStepEvent
  selected: boolean
  onSelect: (stepId: string) => void
  isBranch?: boolean
  highlighted?: boolean
  compact?: boolean
  isNew?: boolean
  onHover?: (stepId: string | null) => void
}

function JsonBlock({ label, data }: { label: string; data: unknown }) {
  const [open, setOpen] = useState(false)
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
        className="font-sans text-[10px] uppercase tracking-wide text-white/45 transition hover:text-white/70 focus-visible:outline focus-visible:outline-1 focus-visible:outline-white/30"
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

export function StepNode({
  step,
  selected,
  onSelect,
  isBranch,
  highlighted,
  compact = false,
  isNew = false,
  onHover,
}: StepNodeProps) {
  const isResolved = step.status === 'success' || step.status === 'failed'
  const [expanded, setExpanded] = useState(!compact && !isResolved)
  const [showNewHighlight, setShowNewHighlight] = useState(isNew)
  const reducedMotion = useReducedMotion()
  const theme = armTheme(step.arm)
  const Icon = TYPE_ICONS[step.type] ?? Wrench
  const ms = latencyMs(step)
  const isRunning = step.status === 'running'
  const isFailed = step.status === 'failed'

  useEffect(() => {
    if (compact && isResolved) setExpanded(false)
  }, [compact, isResolved])

  useEffect(() => {
    if (!isNew || reducedMotion) return
    const timer = setTimeout(() => setShowNewHighlight(false), 1200)
    return () => clearTimeout(timer)
  }, [isNew, reducedMotion])

  const borderColor = isFailed ? '#f87171' : isRunning ? theme.color : isResolved ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.08)'

  const cardContent = (
    <motion.article
      layout={!compact}
      initial={
        compact
          ? reducedMotion
            ? { opacity: isResolved ? 0.65 : 1 }
            : { opacity: 0, y: 6, scale: 0.98 }
          : undefined
      }
      animate={
        compact
          ? reducedMotion
            ? { opacity: isResolved ? 0.65 : 1 }
            : { opacity: isResolved ? 0.65 : 1, y: 0, scale: 1 }
          : undefined
      }
      transition={springEnter(reducedMotion)}
      className={`rounded-lg border border-white/[0.06] bg-white/[0.02] transition-colors ${
        compact ? 'mb-1.5' : 'mb-3'
      } ${onHover ? 'hover:bg-white/[0.04]' : ''} relative`}
      style={{
        borderLeftWidth: 3,
        borderLeftColor: borderColor,
        boxShadow: isRunning
          ? `0 0 12px ${theme.glow}`
          : highlighted
            ? `0 0 8px ${theme.glow}`
            : showNewHighlight
              ? `0 0 16px ${theme.glow}`
              : undefined,
      }}
      onMouseEnter={() => onHover?.(step.step_id)}
      onMouseLeave={() => onHover?.(null)}
    >
      {showNewHighlight && !reducedMotion && (
        <motion.div
          className="pointer-events-none absolute left-0 top-0 bottom-0 w-[3px] rounded-l-lg"
          style={{ backgroundColor: theme.color }}
          initial={{ scaleY: 0, opacity: 1 }}
          animate={{ scaleY: 1, opacity: 0 }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
        />
      )}

      <button
        type="button"
        onClick={() => {
          onSelect(step.step_id)
          setExpanded((e) => !e)
        }}
        className={`flex w-full items-center gap-2 text-left transition active:scale-[0.99] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 ${
          compact ? 'px-2.5 py-1.5' : 'px-3 py-2.5'
        }`}
        style={{
          background: selected ? 'rgba(255,255,255,0.03)' : undefined,
          outlineColor: theme.color,
        }}
      >
        {isResolved && compact ? (
          <Check size={12} className="shrink-0 text-emerald-400/70" />
        ) : (
          <motion.span
            animate={
              isRunning && !reducedMotion
                ? step.type === 'tool_call' || step.type === 'tool_result'
                  ? { scale: [1, 1.15, 1] }
                  : {}
                : {}
            }
            transition={{ duration: 1.2, repeat: isRunning ? Infinity : 0, ease: 'easeInOut' }}
          >
            <Icon size={compact ? 12 : 14} style={{ color: theme.color }} />
          </motion.span>
        )}
        <div className="min-w-0 flex-1">
          <p className={`truncate font-sans text-white/85 ${compact ? 'text-[11px]' : 'text-xs'}`}>
            {step.title}
          </p>
          {!compact && (
            <p className="font-mono text-[10px] uppercase tracking-wide text-white/35">{step.type}</p>
          )}
        </div>
        {compact && (
          <span className="font-mono text-[9px] uppercase tracking-wide text-white/30">{step.type}</span>
        )}
        {isRunning ? (
          <motion.span
            className="rounded px-1.5 py-0.5 font-mono text-[10px]"
            style={{ color: theme.color, border: `1px solid ${theme.border}` }}
            animate={reducedMotion ? {} : { opacity: [1, 0.45, 1] }}
            transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
          >
            running
          </motion.span>
        ) : isResolved && compact ? (
          ms != null ? (
            <span className="font-mono text-[9px] text-white/30">{ms}ms</span>
          ) : (
            <Check size={10} className="text-emerald-400/50" />
          )
        ) : ms != null ? (
          <span className="font-mono text-[10px] text-white/40">{ms}ms</span>
        ) : null}
        <ChevronDown
          size={compact ? 12 : 14}
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
  )

  if (compact) {
    return <div className="relative">{cardContent}</div>
  }

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
      {cardContent}
    </div>
  )
}
