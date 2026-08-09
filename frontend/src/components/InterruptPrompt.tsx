import { useState, useId } from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle, MessageSquare } from 'lucide-react'
import type { RunStepEvent, InterruptResponse } from '../lib/types'
import { armTheme } from '../lib/armTheme'
import { springInterrupt } from '../lib/motion'
import { useReducedMotion } from '../hooks/useAccessibility'
import { PressableButton } from './PressableButton'

interface InterruptPromptProps {
  interrupt: RunStepEvent
  onResponse: (response: InterruptResponse) => void
  isWaitingForInput?: boolean
}

export function InterruptPrompt({ interrupt, onResponse, isWaitingForInput }: InterruptPromptProps) {
  const [alternativeInput, setAlternativeInput] = useState('')
  const [humanResponse, setHumanResponse] = useState('')
  const [submittingDecision, setSubmittingDecision] = useState<string | null>(null)
  const reducedMotion = useReducedMotion()
  const theme = armTheme(interrupt.arm)
  const titleId = useId()
  const descId = useId()

  const payload = interrupt.payload.result as Record<string, unknown> | undefined
  const interruptType = payload?.type as string | undefined

  const handleResponse = async (response: InterruptResponse, decisionKey: string) => {
    setSubmittingDecision(decisionKey)
    try {
      await onResponse(response)
    } finally {
      setSubmittingDecision(null)
    }
  }

  const accentStyle = {
    '--accent': theme.color,
    boxShadow: isWaitingForInput ? `0 0 24px ${theme.glow}, 0 0 0 1px rgba(245,158,11,0.2)` : `0 0 16px ${theme.glow}`,
  } as React.CSSProperties

  const inputClass =
    'rounded border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-sm text-white placeholder-white/30 outline-none transition focus:border-transparent focus:ring-2 disabled:opacity-40'

  const renderContent = () => {
    if (interruptType === 'command_approval') {
      const tool = payload?.tool as string | undefined
      const task = payload?.task as string | undefined
      const command = payload?.command as string | undefined
      const file_path = payload?.file_path as string | undefined
      const path = payload?.path as string | undefined
      const browser_task = payload?.browser_task as string | undefined

      return (
        <>
          <div className="mb-3 flex items-center gap-2" style={{ color: theme.color }}>
            <AlertTriangle size={18} />
            <span className="font-semibold">Approval Required</span>
          </div>
          <div id={descId} className="mb-4 space-y-2 text-sm text-white/80">
            <div><span className="text-white/45">Tool:</span> {tool || 'unknown'}</div>
            {task && <div><span className="text-white/45">Task:</span> {task}</div>}
            {command && (
              <div className="mt-2">
                <div className="text-white/45">Command:</div>
                <code className="mt-1 block rounded bg-black/30 p-2 text-xs text-amber-100/90">{command}</code>
              </div>
            )}
            {file_path && tool === 'write_file_tool' && (
              <div className="mt-2">
                <div className="text-white/45">File:</div>
                <code className="mt-1 block rounded bg-black/30 p-2 text-xs text-amber-100/90">
                  write_file_tool(path="{file_path}", content="&lt;generated content&gt;")
                </code>
              </div>
            )}
            {path !== undefined && tool === 'delete_file_tool' && (
              <div className="mt-2">
                <div className="text-white/45">Delete:</div>
                <code className="mt-1 block rounded bg-black/30 p-2 text-xs text-amber-100/90">
                  delete_file_tool(path="{path || '<workspace>'}"{path === '' ? ' recursive=True' : ''})
                </code>
              </div>
            )}
            {browser_task && (
              <div className="mt-2">
                <div className="text-white/45">Browser Action:</div>
                <code className="mt-1 block rounded bg-black/30 p-2 text-xs text-amber-100/90">{browser_task}</code>
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <PressableButton
              variant="success"
              disabled={submittingDecision !== null}
              onClick={() => handleResponse({ decision: 'approve' }, 'approve')}
            >
              {submittingDecision === 'approve' ? 'Approving...' : 'Approve'}
            </PressableButton>
            <PressableButton
              variant="danger"
              disabled={submittingDecision !== null}
              onClick={() => handleResponse({ decision: 'reject' }, 'reject')}
            >
              {submittingDecision === 'reject' ? 'Rejecting...' : 'Reject'}
            </PressableButton>
            <div className="flex flex-1 gap-2">
              <input
                type="text"
                value={alternativeInput}
                onChange={(e) => setAlternativeInput(e.target.value)}
                placeholder="Alternative..."
                disabled={submittingDecision !== null}
                className={`${inputClass} min-w-0 flex-1`}
                style={{ '--tw-ring-color': theme.color } as React.CSSProperties}
                onFocus={(e) => (e.currentTarget.style.boxShadow = `0 0 0 2px ${theme.color}40`)}
                onBlur={(e) => (e.currentTarget.style.boxShadow = '')}
              />
              <PressableButton
                variant="primary"
                accentColor={theme.color}
                disabled={!alternativeInput.trim() || submittingDecision !== null}
                onClick={() => handleResponse({ decision: 'alternative', alternative_input: alternativeInput }, 'alternative')}
              >
                {submittingDecision === 'alternative' ? 'Sending...' : 'Alternative'}
              </PressableButton>
            </div>
          </div>
        </>
      )
    }

    if (interruptType === 'human_question') {
      const question = payload?.question as string | undefined

      return (
        <>
          <div className="mb-3 flex items-center gap-2 text-blue-300">
            <MessageSquare size={18} />
            <span className="font-semibold">Question from Agent</span>
          </div>
          <div id={descId} className="mb-4 text-sm text-white/80">
            {question || 'No question provided'}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={humanResponse}
              onChange={(e) => setHumanResponse(e.target.value)}
              placeholder="Your answer..."
              disabled={submittingDecision !== null}
              className={`${inputClass} flex-1`}
              style={{ '--tw-ring-color': theme.color } as React.CSSProperties}
              onFocus={(e) => (e.currentTarget.style.boxShadow = `0 0 0 2px ${theme.color}40`)}
              onBlur={(e) => (e.currentTarget.style.boxShadow = '')}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && humanResponse.trim()) {
                  handleResponse({ human_response: humanResponse }, 'send')
                }
              }}
            />
            <PressableButton
              variant="primary"
              accentColor={theme.color}
              disabled={!humanResponse.trim() || submittingDecision !== null}
              onClick={() => handleResponse({ human_response: humanResponse }, 'send')}
            >
              {submittingDecision === 'send' ? 'Sending...' : 'Send'}
            </PressableButton>
          </div>
        </>
      )
    }

    return (
      <div className="text-sm text-white/60">
        Unknown interrupt type: {interruptType || 'unknown'}
      </div>
    )
  }

  return (
    <div className="relative my-4">
      {/* Backdrop blur layer */}
      <div
        className="pointer-events-none absolute -inset-x-4 -inset-y-2 rounded-xl"
        style={{
          background: 'rgba(10,10,12,0.4)',
          backdropFilter: 'blur(8px)',
          WebkitBackdropFilter: 'blur(8px)',
        }}
        aria-hidden
      />

      <motion.div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        initial={reducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 8 }}
        animate={
          reducedMotion
            ? { opacity: 1 }
            : {
                opacity: 1,
                scale: 1,
                y: 0,
                ...(isWaitingForInput && !reducedMotion
                  ? {}
                  : {}),
              }
        }
        transition={springInterrupt(reducedMotion)}
        className="relative overflow-hidden rounded-xl border border-amber-500/30 p-4"
        style={{
          ...accentStyle,
          background: 'rgba(245,158,11,0.08)',
        }}
      >
        {/* Top accent bar */}
        <div
          className="absolute inset-x-0 top-0 h-[2px]"
          style={{
            background: `linear-gradient(90deg, transparent, ${theme.color}, transparent)`,
          }}
        />

        {isWaitingForInput && (
          <motion.div
            className="pointer-events-none absolute inset-0 rounded-xl"
            animate={reducedMotion ? {} : { opacity: [0.3, 0.6, 0.3] }}
            transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
            style={{ boxShadow: `inset 0 0 20px ${theme.glow}` }}
          />
        )}

        <div id={titleId} className="sr-only">
          Agent requires your input
        </div>

        <div className="relative">{renderContent()}</div>
      </motion.div>
    </div>
  )
}
