import { useCallback, useEffect, useState } from 'react'
import type { ChatMessage, InterruptResponse } from '../lib/types'
import { useRunStream } from './useRunStream'
import { toast } from '../components/Toast'

const API_BASE = ''

export function useChatStream(runId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  // Start live=true for a new run; flip to false when the WebSocket signals completion.
  const [isLive, setIsLive] = useState(false)

  // When a new runId arrives (just submitted), assume the run is live immediately.
  useEffect(() => {
    if (!runId) {
      setIsLive(false)
      return
    }
    setIsLive(true)
  }, [runId])

  const { steps, connected, reconnecting } = useRunStream(runId, isLive)

  // Detect run completion from the WebSocket event stream.
  // The backend emits a "run_complete" sentinel event before closing the socket.
  // This replaces the previous 3-second HTTP polling loop for run status.
  useEffect(() => {
    if (!runId) return
    const hasCompletion = steps.order.some(
      (id) => steps.byId[id]?.type === 'run_complete'
    )
    if (hasCompletion) {
      setIsLive(false)
    }
  }, [runId, steps.order, steps.byId])

  // Also flip isLive=false if the WebSocket disconnects cleanly (not reconnecting).
  useEffect(() => {
    if (!runId) return
    if (!connected && !reconnecting && isLive) {
      // Give a short grace period in case it's a transient reconnect
      const timer = setTimeout(() => setIsLive(false), 4000)
      return () => clearTimeout(timer)
    }
  }, [runId, connected, reconnecting, isLive])

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

  useEffect(() => {
    if (!runId) return

    const hasRunningSteps = steps.order.some(id => steps.byId[id]?.status === 'running')
    const hasSynthesis = steps.order.some(id => steps.byId[id]?.type === 'synthesis')

    if ((hasSynthesis || (!hasRunningSteps && steps.order.length > 0)) && steps.order.length > 0) {
      const loadMessages = async () => {
        try {
          const res = await fetch(`${API_BASE}/runs/${runId}/messages`)
          if (res.ok) {
            const chatMessages = await res.json() as ChatMessage[]
            setMessages(chatMessages)
          }
        } catch (error) {
          console.error('Failed to load chat messages after completion:', error)
        }
      }

      const timeoutId = setTimeout(loadMessages, 500)
      return () => clearTimeout(timeoutId)
    }
  }, [runId, steps.order, steps.byId])

  const sendMessage = useCallback(async (content: string) => {
    const tempId = `msg-${Date.now()}`
    const userMessage: ChatMessage = {
      run_id: runId ?? 'pending',
      message_id: tempId,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMessage])

    try {
      const res = await fetch(`${API_BASE}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: content, arm: 'plan_execute_synthesis' }),
      })

      if (!res.ok) {
        if (res.status === 409) {
          toast('A run is already in progress', 'error')
        }
        throw new Error('Failed to create run')
      }

      const run = await res.json()
      toast('Task submitted — agent is working', 'success')
      return run.run_id
    } catch (error) {
      console.error('Failed to send message:', error)
      setMessages((prev) => prev.filter((m) => m.message_id !== tempId))
      if (!(error instanceof Error && error.message === 'Failed to create run')) {
        toast('Failed to send message', 'error')
      }
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
        toast('Failed to submit response', 'error')
        throw new Error('Failed to submit interrupt response')
      }

      toast('Response submitted', 'success')
      return await res.json()
    } catch (error) {
      console.error('Failed to respond to interrupt:', error)
      throw error
    }
  }, [runId])

  const isWaitingForInput = steps.order.some(
    (id) => steps.byId[id]?.type === 'interrupt' && steps.byId[id]?.status === 'running'
  )

  return {
    messages,
    steps,
    connected,
    reconnecting,
    sendMessage,
    respondToInterrupt,
    isWaitingForInput,
  }
}

export { fetchRuns, fetchRun, loadRunSteps } from './useRunStream'
