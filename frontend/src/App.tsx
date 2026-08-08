import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { GitCompare, MessageSquare, Bug } from 'lucide-react'
import type { ArmName, InterruptResponse, RunStepEvent, RunSummary } from './lib/types'
import { RunList } from './components/RunList'
import { Timeline } from './components/Timeline'
import { ContextPanel } from './components/ContextPanel'
import { CompareView } from './components/CompareView'
import { PlaybackScrubber } from './components/PlaybackScrubber'
import { ChatInterface } from './components/ChatInterface'
import { ToastProvider } from './components/Toast'
import { fetchRun, fetchRuns, loadRunSteps, useRunStream } from './hooks/useRunStream'
import { useChatStream } from './hooks/useChatStream'
import { useRunReplay } from './hooks/useRunReplay'
import { armTheme } from './lib/armTheme'
import { springPanel } from './lib/motion'
import { useReducedMotion } from './hooks/useAccessibility'

export default function App() {
  const reducedMotion = useReducedMotion()
  const [mode, setMode] = useState<'chat' | 'debugger'>('chat')
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [hoverStepId, setHoverStepId] = useState<string | null>(null)
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)
  const [armFilter, setArmFilter] = useState<ArmName | 'all'>('all')
  const [passFilter, setPassFilter] = useState<'all' | 'pass' | 'fail'>('all')
  const [replayMode, setReplayMode] = useState(false)

  const selectedRun = runs.find((r) => r.run_id === selectedId) ?? null
  const isLive = selectedRun?.status === 'running' || selectedRun?.status === 'waiting_for_input'

  const debuggerStream = useRunStream(mode === 'debugger' ? selectedId : null, isLive)
  const steps = debuggerStream.steps
  const connected = debuggerStream.connected
  const replay = useRunReplay(steps)

  const {
    messages,
    steps: chatSteps,
    connected: chatConnected,
    reconnecting: chatReconnecting,
    sendMessage,
    respondToInterrupt,
    isWaitingForInput,
  } = useChatStream(mode === 'chat' ? selectedId : null)

  const refreshRuns = useCallback(async () => {
    const list = await fetchRuns()
    setRuns(list)
  }, [])

  useEffect(() => {
    refreshRuns()
    const interval = setInterval(refreshRuns, 5000)
    return () => clearInterval(interval)
  }, [refreshRuns])

  useEffect(() => {
    if (!selectedId || mode !== 'debugger') return
    fetchRun(selectedId).then((detail) => {
      if (detail.status !== 'running') {
        debuggerStream.setSteps(loadRunSteps(detail))
      }
    })
  }, [selectedId, mode])

  useEffect(() => {
    if (selectedRun) setReplayMode(selectedRun.status !== 'running' && selectedRun.status !== 'waiting_for_input')
  }, [selectedRun?.run_id, selectedRun?.status])

  const stepList = useMemo(() => steps.order.map((id) => steps.byId[id]), [steps])
  const selectedStep: RunStepEvent | null = selectedStepId ? steps.byId[selectedStepId] ?? null : null
  const previewStep: RunStepEvent | null = hoverStepId ? steps.byId[hoverStepId] ?? null : null

  const highlightStepId = useMemo(() => {
    if (!replayMode) return null
    const visible = replay.visibleSteps
    return visible.length ? visible[visible.length - 1].step_id : null
  }, [replayMode, replay.visibleSteps])

  const handleSendMessage = useCallback(async (message: string) => {
    const newRunId = await sendMessage(message)
    if (newRunId) {
      setSelectedId(newRunId)
      refreshRuns()
    }
  }, [sendMessage, refreshRuns])

  const handleInterruptResponse = useCallback(async (response: InterruptResponse) => {
    await respondToInterrupt(response)
  }, [respondToInterrupt])

  const activeArm = selectedRun?.arm ?? 'plan_execute_synthesis'
  const theme = armTheme(activeArm)

  return (
    <>
      <div className="grid-bg flex h-screen flex-col bg-canvas text-white">
        <header
          className="relative z-20 flex shrink-0 flex-col border-b border-white/[0.06] border-t border-t-white/[0.06]"
          style={{ background: 'rgba(17,17,20,0.55)', backdropFilter: 'blur(16px)' }}
        >
          <div className="flex items-center justify-between gap-4 px-4 py-3">
            <div className="flex items-center gap-4">
              <div className="flex rounded border border-white/[0.08] p-1">
                <motion.button
                  type="button"
                  layoutId="mode-switch"
                  onClick={() => setMode('chat')}
                  whileTap={reducedMotion ? {} : { scale: 0.96 }}
                  className={`flex items-center gap-2 rounded px-3 py-1.5 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500/50 ${
                    mode === 'chat' ? 'bg-blue-600 text-white' : 'text-white/60 hover:bg-white/[0.04] hover:text-white/80'
                  }`}
                >
                  <MessageSquare size={16} />
                  Chat
                </motion.button>
                <motion.button
                  type="button"
                  onClick={() => setMode('debugger')}
                  whileTap={reducedMotion ? {} : { scale: 0.96 }}
                  className={`flex items-center gap-2 rounded px-3 py-1.5 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500/50 ${
                    mode === 'debugger' ? 'bg-blue-600 text-white' : 'text-white/60 hover:bg-white/[0.04] hover:text-white/80'
                  }`}
                >
                  <Bug size={16} />
                  Debugger
                </motion.button>
              </div>

              <AnimatePresence mode="wait">
                {selectedRun && (
                  <motion.div
                    key={selectedRun.run_id}
                    initial={reducedMotion ? { opacity: 0 } : { opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={reducedMotion ? { opacity: 0 } : { opacity: 0, x: -8 }}
                    transition={springPanel(reducedMotion)}
                    className="hidden min-w-0 sm:block"
                  >
                    {mode === 'debugger' ? (
                      <div>
                        <h1 className="font-sans text-xl font-semibold tracking-[-0.02em] text-white/95">
                          Agent Run Visualizer
                        </h1>
                        <p className="truncate font-mono text-[11px] text-white/40">{selectedRun.task_name}</p>
                      </div>
                    ) : (
                      <p className="truncate font-mono text-[11px] text-white/40">{selectedRun.task_name}</p>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {selectedRun && (
              <motion.span
                layoutId="arm-badge"
                className="shrink-0 rounded px-2 py-0.5 font-sans text-xs"
                style={{
                  color: theme.color,
                  background: theme.bg,
                  border: `1px solid ${theme.border}`,
                }}
              >
                {theme.label}
              </motion.span>
            )}

            {mode === 'debugger' && (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setReplayMode((m) => !m)}
                  className="rounded border border-white/[0.08] px-2 py-1 font-sans text-xs text-white/70 transition hover:bg-white/[0.04] active:scale-95 focus-visible:outline focus-visible:outline-1 focus-visible:outline-white/30"
                  disabled={isLive}
                >
                  {isLive ? 'Live' : replayMode ? 'Replay' : 'Full trace'}
                </button>
                {isLive && (
                  <span className="font-mono text-[10px] text-amber-300/80">
                    {connected ? '● streaming' : debuggerStream.reconnecting ? '◌ reconnecting' : '○ connecting'}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => setCompareOpen(true)}
                  disabled={!selectedRun}
                  className="flex items-center gap-1 rounded border border-white/[0.08] px-2 py-1 font-sans text-xs text-white/70 transition hover:bg-white/[0.04] active:scale-95 disabled:opacity-40 focus-visible:outline focus-visible:outline-1 focus-visible:outline-white/30"
                >
                  <GitCompare size={14} /> Compare
                </button>
              </div>
            )}
          </div>
          {mode === 'debugger' && (
            <PlaybackScrubber
              visible={replayMode && !isLive}
              progress={replay.progress}
              onProgress={replay.setProgress}
            />
          )}
        </header>

        <AnimatePresence mode="wait">
          {mode === 'chat' ? (
            <motion.div
              key="chat"
              initial={reducedMotion ? { opacity: 0 } : { opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reducedMotion ? { opacity: 0 } : { opacity: 0, x: 12 }}
              transition={springPanel(reducedMotion)}
              className="min-h-0 flex-1"
            >
              <ChatInterface
                onSendMessage={handleSendMessage}
                onInterruptResponse={handleInterruptResponse}
                messages={messages}
                steps={chatSteps}
                isWaitingForInput={isWaitingForInput}
                connected={chatConnected}
                reconnecting={chatReconnecting}
                disabled={!!selectedId && !chatConnected && !chatReconnecting}
                arm={activeArm}
                hasActiveRun={!!selectedId && isLive}
              />
            </motion.div>
          ) : (
            <motion.div
              key="debugger"
              initial={reducedMotion ? { opacity: 0 } : { opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reducedMotion ? { opacity: 0 } : { opacity: 0, x: -12 }}
              transition={springPanel(reducedMotion)}
              className="relative flex min-h-0 flex-1"
            >
              <RunList
                runs={runs}
                selectedId={selectedId}
                onSelect={(id) => {
                  setSelectedId(id)
                  setSelectedStepId(null)
                  setHoverStepId(null)
                }}
                collapsed={leftCollapsed}
                onToggleCollapse={() => setLeftCollapsed((c) => !c)}
                armFilter={armFilter}
                passFilter={passFilter}
                onArmFilter={setArmFilter}
                onPassFilter={setPassFilter}
              />

              <main className="min-w-0 flex-1 overflow-y-auto">
                <Timeline
                  steps={steps}
                  visibleIds={replayMode && !isLive ? replay.visibleIds : undefined}
                  selectedStepId={selectedStepId}
                  onSelectStep={(id) => {
                    setSelectedStepId(id)
                    setHoverStepId(null)
                  }}
                  highlightStepId={highlightStepId}
                  onHoverStep={setHoverStepId}
                />
              </main>

              <ContextPanel
                run={selectedRun}
                steps={stepList}
                selectedStep={selectedStep}
                previewStep={previewStep}
                collapsed={rightCollapsed}
                onToggleCollapse={() => setRightCollapsed((c) => !c)}
              />

              <CompareView open={compareOpen} onClose={() => setCompareOpen(false)} primaryRun={selectedRun} runs={runs} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      <ToastProvider />
    </>
  )
}
