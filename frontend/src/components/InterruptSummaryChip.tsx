import { motion } from 'framer-motion'
import { Check, X, MessageSquare, AlertTriangle } from 'lucide-react'
import type { RunStepEvent } from '../lib/types'
import { springEnter } from '../lib/motion'
import { useReducedMotion } from '../hooks/useAccessibility'

interface InterruptSummaryChipProps {
  interrupt: RunStepEvent
  responseSummary?: string
}

function getSummary(interrupt: RunStepEvent, responseSummary?: string): { label: string; icon: typeof Check } {
  if (responseSummary) return { label: responseSummary, icon: Check }

  const payload = interrupt.payload.result as Record<string, unknown> | undefined
  const type = payload?.type as string | undefined

  if (type === 'command_approval') {
    const tool = (payload?.tool as string) ?? 'action'
    if (interrupt.status === 'failed') return { label: `Rejected: ${tool}`, icon: X }
    return { label: `Approved: ${tool}`, icon: Check }
  }

  if (type === 'human_question') {
    return { label: 'Question answered', icon: MessageSquare }
  }

  return { label: 'Interrupt resolved', icon: Check }
}

export function InterruptSummaryChip({ interrupt, responseSummary }: InterruptSummaryChipProps) {
  const reducedMotion = useReducedMotion()
  const { label, icon: Icon } = getSummary(interrupt, responseSummary)
  const isRejected = interrupt.status === 'failed'

  return (
    <motion.div
      initial={reducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.95 }}
      animate={reducedMotion ? { opacity: 1 } : { opacity: 1, scale: 1 }}
      transition={springEnter(reducedMotion)}
      className="my-2 flex items-center gap-2 rounded-full border px-3 py-1.5"
      style={{
        borderColor: isRejected ? 'rgba(248,113,113,0.3)' : 'rgba(52,211,153,0.3)',
        background: isRejected ? 'rgba(248,113,113,0.08)' : 'rgba(52,211,153,0.08)',
      }}
    >
      <Icon size={12} className={isRejected ? 'text-red-400' : 'text-emerald-400'} />
      <span className="font-sans text-xs text-white/60">{label}</span>
      <AlertTriangle size={10} className="ml-auto text-white/25" />
    </motion.div>
  )
}
