import { useEffect, useRef, useMemo, useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { InterruptPrompt } from './InterruptPrompt'
import { StepNode } from './StepNode'
import { AgentActivityIndicator } from './AgentActivityIndicator'
import { ConnectionBanner, ConnectionDot } from './ConnectionBanner'
import { ChatEmptyState } from './ChatEmptyState'
import { InterruptSummaryChip } from './InterruptSummaryChip'
import type {
  ArmName,
  ChatMessage as ChatMessageType,
  InterruptResponse,
  NormalizedSteps,
  RunStepEvent,
} from '../lib/types'

interface ChatInterfaceProps {
  onSendMessage: (message: string) => void
  onInterruptResponse: (response: InterruptResponse) => void
  messages: ChatMessageType[]
  steps: NormalizedSteps
  isWaitingForInput: boolean
  connected: boolean
  reconnecting?: boolean
  disabled?: boolean
  arm?: ArmName
  hasActiveRun?: boolean
}

type TimelineItem =
  | { kind: 'message'; id: string; timestamp: string; message: ChatMessageType }
  | { kind: 'step'; id: string; timestamp: string; step: RunStepEvent }
  | { kind: 'interrupt-active'; id: string; timestamp: string; step: RunStepEvent }
  | { kind: 'interrupt-resolved'; id: string; timestamp: string; step: RunStepEvent; responseSummary?: string }

export function ChatInterface({
  onSendMessage,
  onInterruptResponse,
  messages,
  steps,
  isWaitingForInput,
  connected,
  reconnecting = false,
  disabled = false,
  arm = 'plan_execute_synthesis',
  hasActiveRun = false,
}: ChatInterfaceProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const seenStepIds = useRef<Set<string>>(new Set())
  const [newStepIds, setNewStepIds] = useState<Set<string>>(new Set())
  const [interruptResponses, setInterruptResponses] = useState<Record<string, string>>({})

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, steps, isWaitingForInput])

  // Track newly arrived steps for entrance animation
  useEffect(() => {
    const fresh = new Set<string>()
    for (const id of steps.order) {
      if (!seenStepIds.current.has(id)) {
        seenStepIds.current.add(id)
        fresh.add(id)
      }
    }
    if (fresh.size > 0) {
      setNewStepIds((prev) => new Set([...prev, ...fresh]))
      const timer = setTimeout(() => {
        setNewStepIds((prev) => {
          const next = new Set(prev)
          fresh.forEach((id) => next.delete(id))
          return next
        })
      }, 1500)
      return () => clearTimeout(timer)
    }
  }, [steps.order])

  const activeStep = useMemo(() => {
    const running = steps.order
      .map((id) => steps.byId[id])
      .filter((s) => s && s.status === 'running' && s.type !== 'interrupt')
    return running.length ? running[running.length - 1] : null
  }, [steps])

  const interruptStep = useMemo(
    () =>
      steps.order
        .map((id) => steps.byId[id])
        .filter((s) => s?.type === 'interrupt' && s.status === 'running')
        .sort((a, b) => b.started_at.localeCompare(a.started_at))[0] ?? null,
    [steps],
  )

  const timeline = useMemo((): TimelineItem[] => {
    const items: TimelineItem[] = []

    for (const message of messages) {
      items.push({
        kind: 'message',
        id: message.message_id,
        timestamp: message.timestamp,
        message,
      })
    }

    for (const id of steps.order) {
      const step = steps.byId[id]
      if (!step) continue

      if (step.type === 'interrupt') {
        if (step.status === 'running' && step.step_id === interruptStep?.step_id) {
          items.push({
            kind: 'interrupt-active',
            id: step.step_id,
            timestamp: step.started_at,
            step,
          })
        } else if (step.status !== 'running') {
          items.push({
            kind: 'interrupt-resolved',
            id: `resolved-${step.step_id}`,
            timestamp: step.ended_at ?? step.started_at,
            step,
            responseSummary: interruptResponses[step.step_id],
          })
        }
        continue
      }

      items.push({
        kind: 'step',
        id: step.step_id,
        timestamp: step.started_at,
        step,
      })
    }

    return items.sort((a, b) => a.timestamp.localeCompare(b.timestamp))
  }, [messages, steps, interruptStep, interruptResponses])

  const handleInterruptResponse = async (response: InterruptResponse) => {
    if (interruptStep) {
      let summary = 'Response submitted'
      if (response.decision === 'approve') summary = 'Approved'
      else if (response.decision === 'reject') summary = 'Rejected'
      else if (response.decision === 'alternative') summary = `Alternative: ${response.alternative_input?.slice(0, 40)}…`
      else if (response.human_response) summary = `Answered: ${response.human_response.slice(0, 40)}…`

      setInterruptResponses((prev) => ({ ...prev, [interruptStep.step_id]: summary }))
    }
    await onInterruptResponse(response)
  }

  const isEmpty = messages.length === 0 && steps.order.length === 0
  const isAgentWorking = !!activeStep && !isWaitingForInput
  const isThinking = activeStep?.type === 'reflection' && !isWaitingForInput

  return (
    <div className="flex h-full flex-col bg-canvas text-white">
      <div
        className="border-b border-white/[0.06] px-4 py-3"
        style={{ background: 'rgba(17,17,20,0.55)', backdropFilter: 'blur(16px)' }}
      >
        <div className="flex items-center justify-between">
          <h1 className="font-sans text-xl font-semibold tracking-[-0.02em] text-white/95">Agent Chat</h1>
          {hasActiveRun && <ConnectionDot connected={connected} reconnecting={reconnecting} />}
        </div>
      </div>

      <AnimatePresence>
        {(reconnecting || (!connected && hasActiveRun)) && (
          <ConnectionBanner connected={connected} reconnecting={reconnecting} hasActiveRun={hasActiveRun} />
        )}
      </AnimatePresence>

      <div className="flex-1 overflow-y-auto p-4">
        {isEmpty && <ChatEmptyState onSelectExample={onSendMessage} />}

        {timeline.map((item) => {
          if (item.kind === 'message') {
            return <ChatMessage key={item.id} message={item.message} arm={arm} />
          }

          if (item.kind === 'interrupt-active') {
            return (
              <InterruptPrompt
                key={item.id}
                interrupt={item.step}
                onResponse={handleInterruptResponse}
                isWaitingForInput={isWaitingForInput}
              />
            )
          }

          if (item.kind === 'interrupt-resolved') {
            return (
              <InterruptSummaryChip
                key={item.id}
                interrupt={item.step}
                responseSummary={item.responseSummary}
              />
            )
          }

          return (
            <StepNode
              key={item.id}
              step={item.step}
              selected={false}
              onSelect={() => {}}
              isBranch={!!item.step.parent_step_id}
              compact
              isNew={newStepIds.has(item.step.step_id)}
            />
          )
        })}

        {isAgentWorking && activeStep && (
          <AnimatePresence>
            <div className="sticky bottom-2 mt-2 flex justify-start">
              <AgentActivityIndicator activeStep={activeStep} arm={activeStep.arm} />
            </div>
          </AnimatePresence>
        )}

        <div ref={messagesEndRef} />
      </div>

      <ChatInput
        onSend={onSendMessage}
        disabled={disabled}
        isWaitingForInput={isWaitingForInput}
        isThinking={isThinking}
        thinkingArm={activeStep?.arm}
      />
    </div>
  )
}
