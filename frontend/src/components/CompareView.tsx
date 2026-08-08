import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import type { NormalizedSteps, RunSummary } from '../lib/types'
import { armTheme } from '../lib/armTheme'
import { fetchRun, loadRunSteps } from '../hooks/useRunStream'
import { Timeline } from './Timeline'
import { PlaybackScrubber } from './PlaybackScrubber'
import { useRunReplay } from '../hooks/useRunReplay'
import { springPanel } from '../lib/motion'
import { useReducedMotion, useReducedTransparency } from '../hooks/useAccessibility'

interface CompareViewProps {
  open: boolean
  onClose: () => void
  primaryRun: RunSummary | null
  runs: RunSummary[]
}

export function CompareView({ open, onClose, primaryRun, runs }: CompareViewProps) {
  const reducedMotion = useReducedMotion()
  const reducedTransparency = useReducedTransparency()
  const [secondaryId, setSecondaryId] = useState<string>('')
  const [leftSteps, setLeftSteps] = useState<NormalizedSteps>({ byId: {}, order: [] })
  const [rightSteps, setRightSteps] = useState<NormalizedSteps>({ byId: {}, order: [] })
  const leftScroll = useRef<HTMLDivElement>(null)
  const rightScroll = useRef<HTMLDivElement>(null)
  const syncing = useRef(false)

  const candidates = runs.filter(
    (r) =>
      r.run_id !== primaryRun?.run_id &&
      r.task_name === primaryRun?.task_name &&
      r.arm !== primaryRun?.arm,
  )

  const replayLeft = useRunReplay(leftSteps)
  const replayRight = useRunReplay(rightSteps)
  const sharedProgress = (replayLeft.progress + replayRight.progress) / 2

  useEffect(() => {
    if (!open || !primaryRun) return
    fetchRun(primaryRun.run_id).then((d) => setLeftSteps(loadRunSteps(d)))
  }, [open, primaryRun])

  useEffect(() => {
    if (!secondaryId) return
    fetchRun(secondaryId).then((d) => setRightSteps(loadRunSteps(d)))
  }, [secondaryId])

  useEffect(() => {
    if (candidates.length > 0 && !secondaryId) setSecondaryId(candidates[0].run_id)
  }, [candidates, secondaryId])

  const syncScroll = (source: 'left' | 'right') => {
    if (syncing.current) return
    syncing.current = true
    const from = source === 'left' ? leftScroll.current : rightScroll.current
    const to = source === 'left' ? rightScroll.current : leftScroll.current
    if (from && to) to.scrollTop = from.scrollTop
    requestAnimationFrame(() => {
      syncing.current = false
    })
  }

  const panelBg = reducedTransparency ? 'rgba(10,10,12,0.98)' : 'rgba(10,10,12,0.88)'

  return (
    <AnimatePresence>
      {open && primaryRun && (
        <motion.div
          className="absolute inset-0 z-30 flex flex-col"
          style={{ background: panelBg, backdropFilter: reducedTransparency ? undefined : 'blur(24px)' }}
          initial={reducedMotion ? { opacity: 0 } : { y: 24, opacity: 0 }}
          animate={reducedMotion ? { opacity: 1 } : { y: 0, opacity: 1 }}
          exit={reducedMotion ? { opacity: 0 } : { y: 24, opacity: 0 }}
          transition={springPanel(reducedMotion)}
        >
          <header className="flex items-center justify-between border-b border-white/[0.06] border-t border-t-white/[0.06] px-4 py-3">
            <div>
              <h2 className="font-sans text-lg font-semibold tracking-tight text-white/90">Compare runs</h2>
              <p className="font-mono text-[10px] text-white/40">{primaryRun.task_name}</p>
            </div>
            <div className="flex items-center gap-3">
              <select
                value={secondaryId}
                onChange={(e) => setSecondaryId(e.target.value)}
                className="rounded border border-white/[0.1] bg-white/[0.04] px-2 py-1 font-sans text-xs text-white/80 focus-visible:outline focus-visible:outline-1 focus-visible:outline-white/30"
              >
                {candidates.map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    {armTheme(r.arm).label} — {r.run_id.slice(0, 16)}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={onClose}
                className="rounded p-1 text-white/50 transition hover:bg-white/[0.06] hover:text-white active:scale-95 focus-visible:outline focus-visible:outline-1 focus-visible:outline-white/30"
              >
                <X size={18} />
              </button>
            </div>
          </header>

          <PlaybackScrubber
            visible
            progress={sharedProgress}
            onProgress={(p) => {
              replayLeft.setProgress(p)
              replayRight.setProgress(p)
            }}
          />

          <div className="grid min-h-0 flex-1 grid-cols-2 divide-x divide-white/[0.06]">
            <ComparePane
              run={primaryRun}
              scrollRef={leftScroll}
              onScroll={() => syncScroll('left')}
              steps={leftSteps}
              visibleIds={replayLeft.visibleIds}
              accentSide="left"
            />
            <ComparePane
              run={runs.find((r) => r.run_id === secondaryId) ?? null}
              scrollRef={rightScroll}
              onScroll={() => syncScroll('right')}
              steps={rightSteps}
              visibleIds={replayRight.visibleIds}
              accentSide="right"
            />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function ComparePane({
  run,
  scrollRef,
  onScroll,
  steps,
  visibleIds,
  accentSide,
}: {
  run: RunSummary | null
  scrollRef: React.RefObject<HTMLDivElement>
  onScroll: () => void
  steps: NormalizedSteps
  visibleIds: Set<string>
  accentSide: 'left' | 'right'
}) {
  if (!run) return <div className="p-4 text-white/40">Select a comparison run</div>
  const theme = armTheme(run.arm)

  return (
    <motion.div
      className="flex min-h-0 flex-col"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      <div
        className="border-b border-white/[0.06] px-4 py-2 font-sans text-xs font-medium"
        style={{
          color: theme.color,
          borderLeft: accentSide === 'left' ? `3px solid ${theme.color}` : undefined,
          borderRight: accentSide === 'right' ? `3px solid ${theme.color}` : undefined,
        }}
      >
        {theme.label}
        <span className="ml-2 font-mono text-[10px] text-white/30">
          {steps.order.length} steps
        </span>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto" onScroll={onScroll}>
        <Timeline steps={steps} visibleIds={visibleIds} selectedStepId={null} onSelectStep={() => {}} />
      </div>
    </motion.div>
  )
}
