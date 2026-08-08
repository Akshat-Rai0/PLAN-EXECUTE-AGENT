import { useState } from 'react'
import { AlertTriangle, MessageSquare } from 'lucide-react'
import type { RunStepEvent, InterruptResponse } from '../lib/types'

interface InterruptPromptProps {
  interrupt: RunStepEvent
  onResponse: (response: InterruptResponse) => void
}

export function InterruptPrompt({ interrupt, onResponse }: InterruptPromptProps) {
  const [alternativeInput, setAlternativeInput] = useState('')
  const [humanResponse, setHumanResponse] = useState('')

  const payload = interrupt.payload.result as Record<string, unknown> | undefined
  const interruptType = payload?.type as string | undefined

  if (interruptType === 'command_approval') {
    const tool = payload?.tool as string | undefined
    const task = payload?.task as string | undefined
    const command = payload?.command as string | undefined
    const file_path = payload?.file_path as string | undefined
    const path = payload?.path as string | undefined
    const browser_task = payload?.browser_task as string | undefined

    return (
      <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
        <div className="mb-3 flex items-center gap-2 text-amber-300">
          <AlertTriangle size={20} />
          <span className="font-semibold">Approval Required</span>
        </div>
        <div className="mb-3 space-y-2 text-sm">
          <div><span className="text-white/60">Tool:</span> {tool || 'unknown'}</div>
          {task && <div><span className="text-white/60">Task:</span> {task}</div>}
          {command && (
            <div className="mt-2">
              <div className="text-white/60">Command:</div>
              <code className="mt-1 block rounded bg-black/30 p-2 text-xs text-amber-100">
                {command}
              </code>
            </div>
          )}
          {file_path && (
            <div className="mt-2">
              <div className="text-white/60">File:</div>
              <code className="mt-1 block rounded bg-black/30 p-2 text-xs text-amber-100">
                write_file_tool(path="{file_path}", content="&lt;generated content&gt;")
              </code>
            </div>
          )}
          {path !== undefined && (
            <div className="mt-2">
              <div className="text-white/60">Delete:</div>
              <code className="mt-1 block rounded bg-black/30 p-2 text-xs text-amber-100">
                delete_file_tool(path="{path || '<workspace>'}"{path === '' ? ' recursive=True' : ''})
              </code>
            </div>
          )}
          {browser_task && (
            <div className="mt-2">
              <div className="text-white/60">Browser Action:</div>
              <code className="mt-1 block rounded bg-black/30 p-2 text-xs text-amber-100">
                {browser_task}
              </code>
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => onResponse({ decision: 'approve' })}
            className="rounded bg-green-600 px-3 py-1.5 text-sm text-white transition hover:bg-green-700"
          >
            Approve
          </button>
          <button
            onClick={() => onResponse({ decision: 'reject' })}
            className="rounded bg-red-600 px-3 py-1.5 text-sm text-white transition hover:bg-red-700"
          >
            Reject
          </button>
          <div className="flex gap-2">
            <input
              type="text"
              value={alternativeInput}
              onChange={(e) => setAlternativeInput(e.target.value)}
              placeholder="Alternative..."
              className="w-48 rounded border border-white/[0.06] bg-white/[0.02] px-2 py-1.5 text-sm text-white placeholder-white/30 focus:border-blue-500 focus:outline-none"
            />
            <button
              onClick={() => onResponse({ decision: 'alternative', alternative_input: alternativeInput })}
              disabled={!alternativeInput.trim()}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white transition hover:bg-blue-700 disabled:opacity-50"
            >
              Provide Alternative
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (interruptType === 'human_question') {
    const question = payload?.question as string | undefined

    return (
      <div className="mb-4 rounded-lg border border-blue-500/30 bg-blue-500/10 p-4">
        <div className="mb-3 flex items-center gap-2 text-blue-300">
          <MessageSquare size={20} />
          <span className="font-semibold">Question from Agent</span>
        </div>
        <div className="mb-3 text-sm">{question || 'No question provided'}</div>
        <div className="flex gap-2">
          <input
            type="text"
            value={humanResponse}
            onChange={(e) => setHumanResponse(e.target.value)}
            placeholder="Your answer..."
            className="flex-1 rounded border border-white/[0.06] bg-white/[0.02] px-3 py-1.5 text-sm text-white placeholder-white/30 focus:border-blue-500 focus:outline-none"
          />
          <button
            onClick={() => onResponse({ human_response: humanResponse })}
            disabled={!humanResponse.trim()}
            className="rounded bg-blue-600 px-4 py-1.5 text-sm text-white transition hover:bg-blue-700 disabled:opacity-50"
          >
            Send Response
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="mb-4 rounded-lg border border-gray-500/30 bg-gray-500/10 p-4">
      <div className="text-sm text-gray-300">
        Unknown interrupt type: {interruptType || 'unknown'}
      </div>
    </div>
  )
}
