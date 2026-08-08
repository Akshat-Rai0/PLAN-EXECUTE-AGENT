import { useRef, useEffect } from 'react'
import { motion, useMotionValue, useTransform, animate, useSpring } from 'framer-motion'
import { springScrubber } from '../lib/motion'
import { useReducedMotion } from '../hooks/useAccessibility'

interface PlaybackScrubberProps {
  progress: number
  onProgress: (p: number) => void
  visible: boolean
}

export function PlaybackScrubber({ progress, onProgress, visible }: PlaybackScrubberProps) {
  const reducedMotion = useReducedMotion()
  const trackRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const x = useMotionValue(progress * 100)
  const springX = useSpring(x, reducedMotion ? { duration: 0 } : { stiffness: 400, damping: 30 })
  const widthPct = useTransform(springX, (v) => `${Math.max(0, Math.min(100, v))}%`)
  const thumbLeft = useTransform(springX, (v) => `${Math.max(0, Math.min(100, v))}%`)

  useEffect(() => {
    if (!dragging.current) {
      if (reducedMotion) {
        x.set(progress * 100)
      } else {
        animate(x, progress * 100, springScrubber(reducedMotion))
      }
    }
  }, [progress, reducedMotion, x])

  if (!visible) return null

  const handlePointer = (clientX: number) => {
    const track = trackRef.current
    if (!track) return
    const rect = track.getBoundingClientRect()
    const p = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    onProgress(p)
    x.set(p * 100)
  }

  return (
    <div className="px-4 py-2">
      <div
        ref={trackRef}
        className="relative h-2 cursor-pointer rounded-full bg-white/[0.08] transition hover:bg-white/[0.1]"
        onPointerDown={(e) => {
          dragging.current = true
          e.currentTarget.setPointerCapture(e.pointerId)
          handlePointer(e.clientX)
        }}
        onPointerMove={(e) => {
          if (!dragging.current) return
          handlePointer(e.clientX)
        }}
        onPointerUp={(e) => {
          dragging.current = false
          e.currentTarget.releasePointerCapture(e.pointerId)
          if (!reducedMotion) {
            animate(x, progress * 100, springScrubber(reducedMotion))
          }
        }}
        role="slider"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress * 100)}
        aria-label="Playback scrubber"
      >
        <motion.div className="absolute inset-y-0 left-0 rounded-full bg-white/25" style={{ width: widthPct }} />
        <motion.div
          className="absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full border border-white/40 bg-white/95 shadow-md"
          style={{ left: thumbLeft, x: '-50%' }}
          whileHover={reducedMotion ? {} : { scale: 1.15 }}
          whileTap={reducedMotion ? {} : { scale: 0.9 }}
        />
      </div>
      <p className="mt-1 text-center font-mono text-[10px] text-white/35">
        {Math.round(progress * 100)}% through run
      </p>
    </div>
  )
}
