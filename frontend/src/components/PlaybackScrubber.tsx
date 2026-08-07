import { useRef } from 'react'
import { motion, useMotionValue, useTransform, animate } from 'framer-motion'
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
  const widthPct = useTransform(x, (v) => `${Math.max(0, Math.min(100, v))}%`)
  const thumbLeft = useTransform(x, (v) => `${Math.max(0, Math.min(100, v))}%`)

  if (!visible) return null

  const handlePointer = (clientX: number, springOnRelease: boolean) => {
    const track = trackRef.current
    if (!track) return
    const rect = track.getBoundingClientRect()
    const p = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    onProgress(p)
    if (dragging.current) {
      x.set(p * 100)
    } else if (springOnRelease && !reducedMotion) {
      animate(x, p * 100, springScrubber(reducedMotion))
    } else {
      x.set(p * 100)
    }
  }

  return (
    <div className="px-4 py-2">
      <div
        ref={trackRef}
        className="relative h-2 cursor-pointer rounded-full bg-white/[0.08]"
        onPointerDown={(e) => {
          dragging.current = true
          e.currentTarget.setPointerCapture(e.pointerId)
          handlePointer(e.clientX, false)
        }}
        onPointerMove={(e) => {
          if (!dragging.current) return
          handlePointer(e.clientX, false)
        }}
        onPointerUp={() => {
          dragging.current = false
        }}
        role="slider"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress * 100)}
        aria-label="Playback scrubber"
      >
        <motion.div className="absolute inset-y-0 left-0 rounded-full bg-white/25" style={{ width: widthPct }} />
        <motion.div
          className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border border-white/30 bg-white/90"
          style={{ left: thumbLeft, x: '-50%' }}
        />
      </div>
      <p className="mt-1 text-center font-mono text-[10px] text-white/35">
        {Math.round(progress * 100)}% through run
      </p>
    </div>
  )
}
