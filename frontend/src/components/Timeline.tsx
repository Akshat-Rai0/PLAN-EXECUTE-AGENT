import type { NormalizedSteps, RunStepEvent } from '../lib/types'
import { StepNode } from './StepNode'

interface TimelineProps {
  steps: NormalizedSteps
  visibleIds?: Set<string>
  selectedStepId: string | null
  onSelectStep: (stepId: string) => void
  highlightStepId?: string | null
}

export function Timeline({ steps, visibleIds, selectedStepId, onSelectStep, highlightStepId }: TimelineProps) {
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
          />
        )
      })}
    </div>
  )
}
