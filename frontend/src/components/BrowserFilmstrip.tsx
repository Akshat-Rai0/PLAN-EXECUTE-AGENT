import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useReducedMotion } from '../hooks/useAccessibility'

interface BrowserFilmstripProps {
  screenshotUrl: string
  title?: string
  previousUrl?: string | null
}

export function BrowserFilmstrip({ screenshotUrl, title, previousUrl }: BrowserFilmstripProps) {
  const reducedMotion = useReducedMotion()
  const prevUrlRef = useRef<string | null>(null)

  useEffect(() => {
    prevUrlRef.current = previousUrl ?? null
  }, [screenshotUrl, previousUrl])

  return (
    <div className="mt-2 overflow-hidden rounded border border-white/[0.08]">
      <div className="border-b border-white/[0.06] bg-white/[0.03] px-2 py-1 font-mono text-[10px] text-white/40">
        {title ?? 'Browser screenshot'}
      </div>
      <div className="relative max-h-48 w-full overflow-hidden bg-black/20">
        <AnimatePresence mode="sync">
          <motion.img
            key={screenshotUrl}
            src={screenshotUrl}
            alt={title ?? 'Browser step screenshot'}
            className="max-h-48 w-full object-cover object-top"
            loading="lazy"
            initial={reducedMotion ? { opacity: 1 } : { opacity: 0, x: 12 }}
            animate={reducedMotion ? { opacity: 1 } : { opacity: 1, x: 0 }}
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, x: -12 }}
            transition={{ duration: reducedMotion ? 0.01 : 0.35, ease: 'easeOut' }}
          />
        </AnimatePresence>
      </div>
    </div>
  )
}
