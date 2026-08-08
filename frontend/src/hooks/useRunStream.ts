import { useCallback, useEffect, useRef, useState } from 'react'
import type { NormalizedSteps, RunStepEvent } from '../lib/types'
import { mergeStep, normalizeSteps } from '../lib/types'

const API_BASE = ''
const MAX_RECONNECT_ATTEMPTS = 8
const BASE_RECONNECT_MS = 1000

export function useRunStream(runId: string | null, isLive: boolean) {
  const [steps, setSteps] = useState<NormalizedSteps>({ byId: {}, order: [] })
  const [connected, setConnected] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const bufferRef = useRef<RunStepEvent[]>([])
  const rafRef = useRef<number | null>(null)
  const reconnectAttemptRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const flushBuffer = useCallback(() => {
    if (bufferRef.current.length === 0) return
    const batch = bufferRef.current.splice(0)
    setSteps((prev) => {
      const byId = { ...prev.byId }
      const order = [...prev.order]
      for (const event of batch) {
        byId[event.step_id] = mergeStep(byId[event.step_id], event)
        if (!order.includes(event.step_id)) order.push(event.step_id)
      }
      order.sort((a, b) => byId[a].started_at.localeCompare(byId[b].started_at))
      return { byId, order }
    })
  }, [])

  const scheduleFlush = useCallback(() => {
    if (rafRef.current !== null) return
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null
      flushBuffer()
    })
  }, [flushBuffer])

  useEffect(() => {
    if (!runId) {
      setSteps({ byId: {}, order: [] })
      setConnected(false)
      setReconnecting(false)
      return
    }

    let cancelled = false
    let ws: WebSocket | null = null

    const connect = () => {
      if (cancelled) return

      const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const wsHost = import.meta.env.DEV ? '127.0.0.1:8000' : window.location.host
      ws = new WebSocket(`${wsProtocol}://${wsHost}/runs/${runId}/stream`)

      ws.onopen = () => {
        if (cancelled) return
        reconnectAttemptRef.current = 0
        setConnected(true)
        setReconnecting(false)
      }

      ws.onmessage = (msg) => {
        const event = JSON.parse(msg.data) as RunStepEvent
        bufferRef.current.push(event)
        scheduleFlush()
      }

      ws.onclose = () => {
        if (cancelled) return
        setConnected(false)
        flushBuffer()

        if (isLive && reconnectAttemptRef.current < MAX_RECONNECT_ATTEMPTS) {
          setReconnecting(true)
          const delay = BASE_RECONNECT_MS * Math.pow(1.5, reconnectAttemptRef.current)
          reconnectAttemptRef.current += 1
          reconnectTimerRef.current = setTimeout(connect, delay)
        } else {
          setReconnecting(false)
        }
      }

      ws.onerror = () => {
        ws?.close()
      }
    }

    connect()

    return () => {
      cancelled = true
      ws?.close()
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      reconnectAttemptRef.current = 0
    }
  }, [runId, isLive, flushBuffer, scheduleFlush])

  return { steps, connected, reconnecting, setSteps }
}

export async function fetchRuns(): Promise<import('../lib/types').RunSummary[]> {
  const res = await fetch(`${API_BASE}/runs`)
  if (!res.ok) throw new Error('Failed to fetch runs')
  return res.json()
}

export async function fetchRun(runId: string): Promise<import('../lib/types').RunDetail> {
  const res = await fetch(`${API_BASE}/runs/${runId}`)
  if (!res.ok) throw new Error('Failed to fetch run')
  return res.json()
}

export function loadRunSteps(detail: import('../lib/types').RunDetail): NormalizedSteps {
  return normalizeSteps(detail.steps)
}
