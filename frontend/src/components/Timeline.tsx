import { useRef, useEffect, useState } from 'react'
import type { NormalizedSteps, RunStepEvent } from '../lib/types'
import { StepNode } from './StepNode'

interface TimelineProps {
  steps: NormalizedSteps
  visibleIds?: Set<string>
  selectedStepId: string | null
  onSelectStep: (stepId: string) => void
  highlightStepId?: string | null
  onHoverStep?: (stepId: string | null) => void
  newStepIds?: Set<string>
}

export function Timeline({
  steps,
  visibleIds,
  selectedStepId,
  onSelectStep,
  highlightStepId,
  onHoverStep,
  newStepIds,
}: TimelineProps) {
  const seenStepIds = useRef<Set<string>>(new Set())
  const [internalNewIds, setInternalNewIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    const fresh = new Set<string>()
    for (const id of steps.order) {
      if (!seenStepIds.current.has(id)) {
        seenStepIds.current.add(id)
        fresh.add(id)
      }
    }
    if (fresh.size > 0) {
      setInternalNewIds((prev) => new Set([...prev, ...fresh]))
      const timer = setTimeout(() => {
        setInternalNewIds((prev) => {
          const next = new Set(prev)
          fresh.forEach((id) => next.delete(id))
          return next
        })
      }, 1500)
      return () => clearTimeout(timer)
    }
  }, [steps.order])

  const ordered = steps.order
    .map((id) => steps.byId[id])
    .filter((s): s is RunStepEvent => !!s)
    .filter((s) => !visibleIds || visibleIds.has(s.step_id))

  if (ordered.length === 0) {
    return (
      <div className="flex h-full items-center justify-center font-sans text-sm text-white/35">
        Select a run to view its trace timeline
      </div>
    )
  }

  const effectiveNewIds = newStepIds ?? internalNewIds

  return (
    <div className="mx-auto max-w-2xl py-6 pr-4">
      {ordered.map((step) => {
        const isBranch = !!step.parent_step_id
        return (
          <StepNode
            key={step.step_id}
            step={step}
            selected={selectedStepId === step.step_id}
            onSelect={onSelectStep}
            isBranch={isBranch}
            highlighted={highlightStepId === step.step_id}
            onHover={onHoverStep}
            isNew={effectiveNewIds.has(step.step_id)}
          />
        )
      })}
    </div>
  )
}
