import { motion } from 'framer-motion'
import { Map, RefreshCw, Sparkles, Globe, Wrench } from 'lucide-react'
import type { ArmName, RunStepEvent } from '../lib/types'
import { armTheme } from '../lib/armTheme'
import { useReducedMotion } from '../hooks/useAccessibility'

interface AgentActivityIndicatorProps {
  activeStep: RunStepEvent | null
  arm: ArmName
}

export function AgentActivityIndicator({ activeStep, arm }: AgentActivityIndicatorProps) {
  const reducedMotion = useReducedMotion()
  const theme = armTheme(arm)

  if (!activeStep || activeStep.status !== 'running') return null

  const renderIndicator = () => {
    switch (activeStep.type) {
      case 'plan':
        return (
          <div className="flex items-center gap-2">
            <Map size={14} style={{ color: theme.color }} />
            <div className="flex h-1.5 w-16 overflow-hidden rounded-full bg-white/[0.08]">
              <motion.div
                className="h-full rounded-full"
                style={{ backgroundColor: theme.color }}
                initial={{ width: '0%' }}
                animate={reducedMotion ? { width: '100%' } : { width: ['0%', '100%'] }}
                transition={
                  reducedMotion
                    ? {}
                    : { duration: 1.5, repeat: Infinity, ease: 'easeInOut' }
                }
              />
            </div>
            <span className="text-xs text-white/70">Planning...</span>
          </div>
        )

      case 'replan':
        return (
          <div className="flex items-center gap-2">
            <motion.div
              animate={reducedMotion ? {} : { rotate: 360 }}
              transition={reducedMotion ? {} : { duration: 2, repeat: Infinity, ease: 'linear' }}
            >
              <RefreshCw size={14} style={{ color: theme.color }} />
            </motion.div>
            <span className="text-xs text-white/70">Replanning...</span>
          </div>
        )

      case 'browser_step':
        return (
          <div className="flex items-center gap-2">
            <Globe size={14} style={{ color: theme.color }} />
            <div className="relative flex h-1.5 w-16 overflow-hidden rounded-full bg-white/[0.08]">
              <div
                className="absolute inset-y-0 left-0 w-1/3 rounded-full"
                style={{
                  backgroundColor: theme.color,
                  animation: reducedMotion ? 'none' : 'shimmer 1.5s infinite linear',
                }}
              />
            </div>
            <span className="text-xs text-white/70">Browsing...</span>
          </div>
        )

      case 'synthesis':
        return (
          <div className="flex items-center gap-2">
            <motion.div
              animate={reducedMotion ? {} : { rotate: [0, -10, 10, 0] }}
              transition={reducedMotion ? {} : { duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            >
              <Sparkles size={14} style={{ color: theme.color }} />
            </motion.div>
            <span className="text-xs text-white/70">Synthesizing...</span>
          </div>
        )

      case 'tool_call':
      case 'tool_result':
      case 'reflection':
      default:
        return (
          <div className="flex items-center gap-2">
            <Wrench size={14} style={{ color: theme.color }} />
            <motion.div
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: theme.pulse }}
              animate={reducedMotion ? {} : { opacity: [0.3, 1, 0.3], scale: [0.8, 1.1, 0.8] }}
              transition={reducedMotion ? {} : { duration: 1.2, repeat: Infinity, ease: 'easeInOut' }}
            />
            <span className="text-xs text-white/70">Using tool...</span>
          </div>
        )
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 5 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 5 }}
      className="inline-flex items-center rounded-full border border-white/[0.06] bg-white/[0.02] px-3 py-1.5"
      style={{ boxShadow: `0 0 12px ${theme.glow}` }}
    >
      {renderIndicator()}
    </motion.div>
  )
}
