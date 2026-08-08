import { useEffect, useRef } from 'react'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { InterruptPrompt } from './InterruptPrompt'
import type { ChatMessage as ChatMessageType, InterruptResponse, NormalizedSteps } from '../lib/types'

interface ChatInterfaceProps {
  onSendMessage: (message: string) => void
  onInterruptResponse: (response: InterruptResponse) => void
  messages: ChatMessageType[]
  steps: NormalizedSteps
  isWaitingForInput: boolean
  disabled?: boolean
}

export function ChatInterface({
  onSendMessage,
  onInterruptResponse,
  messages,
  steps,
  isWaitingForInput,
  disabled = false,
}: ChatInterfaceProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, steps])

  // Find the most recent interrupt step
  const interruptStep = steps.order
    .map((id) => steps.byId[id])
    .filter((s) => s.type === 'interrupt' && s.status === 'running')
    .sort((a, b) => b.started_at.localeCompare(a.started_at))[0]

  return (
    <div className="flex h-screen flex-col bg-canvas text-white">
      <div className="border-b border-white/[0.06] px-4 py-3">
        <h1 className="font-sans text-xl font-semibold tracking-[-0.02em] text-white/95">
          Agent Chat
        </h1>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {messages.length === 0 && steps.order.length === 0 && (
          <div className="flex h-full items-center justify-center text-white/40">
            <p>Start a conversation by entering a task below</p>
          </div>
        )}

        {messages.map((message) => (
          <ChatMessage key={message.message_id} message={message} />
        ))}

        {interruptStep && (
          <InterruptPrompt
            interrupt={interruptStep}
            onResponse={onInterruptResponse}
          />
        )}

        <div ref={messagesEndRef} />
      </div>

      <ChatInput onSend={onSendMessage} disabled={disabled || isWaitingForInput} />
    </div>
  )
}
