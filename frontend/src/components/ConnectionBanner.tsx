import { motion } from 'framer-motion'
import { WifiOff, Loader2 } from 'lucide-react'
import { useReducedMotion } from '../hooks/useAccessibility'

interface ConnectionBannerProps {
  connected: boolean
  reconnecting?: boolean
  hasActiveRun?: boolean
}

export function ConnectionBanner({ connected, reconnecting, hasActiveRun }: ConnectionBannerProps) {
  const reducedMotion = useReducedMotion()

  if (connected && !reconnecting) return null
  if (!hasActiveRun && !reconnecting) return null

  const isReconnecting = reconnecting || (!connected && hasActiveRun)

  return (
    <motion.div
      initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -4 }}
      animate={reducedMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
      exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -4 }}
      className="flex items-center gap-2 border-b border-amber-500/20 bg-amber-500/10 px-4 py-2 text-xs text-amber-200/90"
      role="status"
      aria-live="polite"
    >
      {isReconnecting ? (
        <>
          <motion.span
            animate={reducedMotion ? {} : { rotate: 360 }}
            transition={reducedMotion ? {} : { duration: 1.5, repeat: Infinity, ease: 'linear' }}
          >
            <Loader2 size={14} className="text-amber-400" />
          </motion.span>
          <span>Reconnecting to live stream…</span>
          <motion.span
            className="ml-auto h-2 w-2 rounded-full bg-amber-400"
            animate={reducedMotion ? { opacity: 0.7 } : { opacity: [0.4, 1, 0.4] }}
            transition={reducedMotion ? {} : { duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            aria-hidden
          />
        </>
      ) : (
        <>
          <WifiOff size={14} className="text-amber-400" />
          <span>Stream disconnected — updates may be stale</span>
        </>
      )}
    </motion.div>
  )
}

export function ConnectionDot({ connected, reconnecting }: { connected: boolean; reconnecting?: boolean }) {
  const reducedMotion = useReducedMotion()

  if (connected && !reconnecting) {
    return (
      <span className="flex items-center gap-1.5 font-mono text-[10px] text-emerald-400/80">
        <span className="relative flex h-2 w-2">
          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
        </span>
        live
      </span>
    )
  }

  return (
    <span className="flex items-center gap-1.5 font-mono text-[10px] text-amber-300/80">
      <span className="relative flex h-2 w-2">
        <motion.span
          className="absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-60"
          animate={reducedMotion ? {} : { scale: [1, 1.6, 1], opacity: [0.7, 0, 0.7] }}
          transition={reducedMotion ? {} : { duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-400" />
      </span>
      {reconnecting ? 'reconnecting' : 'connecting'}
    </span>
  )
}
