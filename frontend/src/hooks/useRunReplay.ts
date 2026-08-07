import { useCallback, useMemo, useState } from 'react'
import type { NormalizedSteps, RunStepEvent } from '../lib/types'

export function useRunReplay(steps: NormalizedSteps) {
  const [virtualNow, setVirtualNow] = useState<number>(() => Date.now())

  const bounds = useMemo(() => {
    const all = steps.order.map((id) => steps.byId[id])
    if (all.length === 0) return { min: 0, max: Date.now() }
    const times = all.flatMap((s) => [
      new Date(s.started_at).getTime(),
      s.ended_at ? new Date(s.ended_at).getTime() : new Date(s.started_at).getTime(),
    ])
    return { min: Math.min(...times), max: Math.max(...times) }
  }, [steps])

  const visibleSteps = useMemo(() => {
    const visible: RunStepEvent[] = []
    for (const id of steps.order) {
      const step = steps.byId[id]
      if (new Date(step.started_at).getTime() <= virtualNow) visible.push(step)
    }
    return visible
  }, [steps, virtualNow])

  const progress = bounds.max === bounds.min ? 1 : (virtualNow - bounds.min) / (bounds.max - bounds.min)

  const setProgress = useCallback(
    (p: number) => {
      const clamped = Math.max(0, Math.min(1, p))
      setVirtualNow(bounds.min + clamped * (bounds.max - bounds.min))
    },
    [bounds],
  )

  const resetToEnd = useCallback(() => setVirtualNow(bounds.max), [bounds.max])
  const resetToStart = useCallback(() => setVirtualNow(bounds.min), [bounds.min])

  return {
    virtualNow,
    setVirtualNow,
    setProgress,
    progress,
    bounds,
    visibleSteps,
    visibleIds: new Set(visibleSteps.map((s) => s.step_id)),
    resetToEnd,
    resetToStart,
  }
}
