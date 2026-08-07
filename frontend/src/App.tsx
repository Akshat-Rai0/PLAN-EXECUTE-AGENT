import { useCallback, useEffect, useMemo, useState } from 'react'
import { GitCompare } from 'lucide-react'
import type { ArmName, RunStepEvent, RunSummary } from './lib/types'
import { RunList } from './components/RunList'
import { Timeline } from './components/Timeline'
import { ContextPanel } from './components/ContextPanel'
import { CompareView } from './components/CompareView'
import { PlaybackScrubber } from './components/PlaybackScrubber'
import { fetchRun, fetchRuns, loadRunSteps, useRunStream } from './hooks/useRunStream'
import { useRunReplay } from './hooks/useRunReplay'
import { armTheme } from './lib/armTheme'

export default function App() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)
  const [armFilter, setArmFilter] = useState<ArmName | 'all'>('all')
  const [passFilter, setPassFilter] = useState<'all' | 'pass' | 'fail'>('all')
  const [replayMode, setReplayMode] = useState(false)

  const selectedRun = runs.find((r) => r.run_id === selectedId) ?? null
  const isLive = selectedRun?.status === 'running'

  const { steps, connected } = useRunStream(selectedId, isLive)
  const replay = useRunReplay(steps)

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
    if (!selectedId) return
    fetchRun(selectedId).then((detail) => {
      if (detail.status !== 'running') {
        loadRunSteps(detail)
      }
    })
  }, [selectedId])

  useEffect(() => {
    if (selectedRun) setReplayMode(selectedRun.status !== 'running')
  }, [selectedRun?.run_id, selectedRun?.status])

  const stepList = useMemo(() => steps.order.map((id) => steps.byId[id]), [steps])
  const selectedStep: RunStepEvent | null = selectedStepId ? steps.byId[selectedStepId] ?? null : null

  const highlightStepId = useMemo(() => {
    if (!replayMode) return null
    const visible = replay.visibleSteps
    return visible.length ? visible[visible.length - 1].step_id : null
  }, [replayMode, replay.visibleSteps])

  return (
    <div className="grid-bg flex h-screen flex-col bg-canvas text-white">
      <header
        className="relative z-20 flex shrink-0 flex-col border-b border-white/[0.06] border-t border-t-white/[0.06]"
        style={{ background: 'rgba(17,17,20,0.55)', backdropFilter: 'blur(16px)' }}
      >
        <div className="flex items-center justify-between gap-4 px-4 py-3">
          <div className="min-w-0 flex-1">
            <h1 className="font-sans text-xl font-semibold tracking-[-0.02em] text-white/95">
              Agent Run Visualizer
            </h1>
            {selectedRun && (
              <p className="truncate font-mono text-[11px] text-white/40">{selectedRun.task_name}</p>
            )}
          </div>
          {selectedRun && (
            <span
              className="shrink-0 rounded px-2 py-0.5 font-sans text-xs"
              style={{
                color: armTheme(selectedRun.arm).color,
                background: armTheme(selectedRun.arm).bg,
                border: `1px solid ${armTheme(selectedRun.arm).border}`,
              }}
            >
              {armTheme(selectedRun.arm).label}
            </span>
          )}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setReplayMode((m) => !m)}
              className="rounded border border-white/[0.08] px-2 py-1 font-sans text-xs text-white/70 transition "
              disabled={isLive}
            >
              {isLive ? 'Live' : replayMode ? 'Replay' : 'Full trace'}
            </button>
            {isLive && (
              <span className="font-mono text-[10px] text-amber-300/80">{connected ? '● streaming' : '○ connecting'}</span>
            )}
            <button
              type="button"
              onClick={() => setCompareOpen(true)}
              disabled={!selectedRun}
              className="flex items-center gap-1 rounded border border-white/[0.08] px-2 py-1 font-sans text-xs text-white/70 transition disabled:opacity-40"
            >
              <GitCompare size={14} /> Compare
            </button>
          </div>
        </div>
        <PlaybackScrubber
          visible={replayMode && !isLive}
          progress={replay.progress}
          onProgress={replay.setProgress}
        />
      </header>

      <div className="relative flex min-h-0 flex-1">
        <RunList
          runs={runs}
          selectedId={selectedId}
          onSelect={(id) => {
            setSelectedId(id)
            setSelectedStepId(null)
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
            onSelectStep={setSelectedStepId}
            highlightStepId={highlightStepId}
          />
        </main>

        <ContextPanel
          run={selectedRun}
          steps={stepList}
          selectedStep={selectedStep}
          collapsed={rightCollapsed}
          onToggleCollapse={() => setRightCollapsed((c) => !c)}
        />

        <CompareView open={compareOpen} onClose={() => setCompareOpen(false)} primaryRun={selectedRun} runs={runs} />
      </div>
    </div>
  )
}
