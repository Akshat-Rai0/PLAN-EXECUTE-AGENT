import { useCallback, useEffect, useState } from 'react'
import type { ChatMessage, InterruptResponse } from '../lib/types'
import { fetchRun, fetchRuns, loadRunSteps, useRunStream } from './useRunStream'

const API_BASE = ''

export function useChatStream(runId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const { steps, connected } = useRunStream(runId, true)

  // Load chat messages when runId changes
  useEffect(() => {
    if (!runId) {
      setMessages([])
      return
    }

    const loadMessages = async () => {
      try {
        const res = await fetch(`${API_BASE}/runs/${runId}/messages`)
        if (res.ok) {
          const chatMessages = await res.json() as ChatMessage[]
          setMessages(chatMessages)
        }
      } catch (error) {
        console.error('Failed to load chat messages:', error)
      }
    }

    loadMessages()
  }, [runId])

  const sendMessage = useCallback(async (content: string) => {
    // Add user message to local state immediately
    const tempId = `msg-${Date.now()}`
    const userMessage: ChatMessage = {
      run_id: runId ?? 'pending',
      message_id: tempId,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMessage])

    // Create a new run with the user's message
    try {
      const res = await fetch(`${API_BASE}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: content, arm: 'plan_execute_synthesis' }),
      })

      if (!res.ok) {
        throw new Error('Failed to create run')
      }

      const run = await res.json()
      // The run will be tracked by the parent component via runId state
      return run.run_id
    } catch (error) {
      console.error('Failed to send message:', error)
      // Remove the user message if run creation failed
      setMessages((prev) => prev.filter((m) => m.message_id !== tempId))
      throw error
    }
  }, [runId])

  const respondToInterrupt = useCallback(async (response: InterruptResponse) => {
    if (!runId) return

    try {
      const res = await fetch(`${API_BASE}/runs/${runId}/interrupt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(response),
      })

      if (!res.ok) {
        throw new Error('Failed to submit interrupt response')
      }

      return await res.json()
    } catch (error) {
      console.error('Failed to respond to interrupt:', error)
      throw error
    }
  }, [runId])

  // Check if run is waiting for input
  const isWaitingForInput = steps.order.some(
    (id) => steps.byId[id]?.type === 'interrupt' && steps.byId[id]?.status === 'running'
  )

  return {
    messages,
    steps,
    connected,
    sendMessage,
    respondToInterrupt,
    isWaitingForInput,
  }
}

export { fetchRuns, fetchRun, loadRunSteps }
