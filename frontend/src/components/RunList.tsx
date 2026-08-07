import { motion } from 'framer-motion'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { ArmName, RunSummary } from '../lib/types'
import { armTheme } from '../lib/armTheme'
import { springPanel } from '../lib/motion'
import { useReducedMotion, useReducedTransparency } from '../hooks/useAccessibility'

interface RunListProps {
  runs: RunSummary[]
  selectedId: string | null
  onSelect: (runId: string) => void
  collapsed: boolean
  onToggleCollapse: () => void
  armFilter: ArmName | 'all'
  passFilter: 'all' | 'pass' | 'fail'
  onArmFilter: (v: ArmName | 'all') => void
  onPassFilter: (v: 'all' | 'pass' | 'fail') => void
}

function StatusDot({ status }: { status: RunSummary['status'] }) {
  const color =
    status === 'running' ? '#fbbf24' : status === 'success' ? '#34d399' : '#f87171'
  return (
    <span className="relative flex h-2 w-2 shrink-0">
      {status === 'running' && (
        <motion.span
          className="absolute inline-flex h-full w-full rounded-full opacity-60"
          style={{ backgroundColor: color }}
          animate={{ scale: [1, 1.8, 1], opacity: [0.7, 0, 0.7] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
      <span className="relative inline-flex h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
    </span>
  )
}

export function RunList({
  runs,
  selectedId,
  onSelect,
  collapsed,
  onToggleCollapse,
  armFilter,
  passFilter,
  onArmFilter,
  onPassFilter,
}: RunListProps) {
  const reducedMotion = useReducedMotion()
  const reducedTransparency = useReducedTransparency()

  const filtered = runs.filter((r) => {
    if (armFilter !== 'all' && r.arm !== armFilter) return false
    if (passFilter === 'pass' && r.pass_fail !== true) return false
    if (passFilter === 'fail' && r.pass_fail !== false) return false
    return true
  })

  const panelBg = reducedTransparency ? 'rgba(17,17,20,0.95)' : 'rgba(17,17,20,0.75)'

  return (
    <motion.aside
      className="flex h-full flex-col border-r border-white/[0.06] border-t border-t-white/[0.06]"
      style={{
        background: panelBg,
        backdropFilter: reducedTransparency ? undefined : 'blur(20px)',
      }}
      animate={{ width: collapsed ? 48 : 280 }}
      transition={springPanel(reducedMotion)}
    >
      <div className="flex items-center justify-between border-b border-white/[0.06] px-3 py-3">
        {!collapsed && <h2 className="font-sans text-sm font-semibold tracking-tight text-white/90">Runs</h2>}
        <button
          type="button"
          onClick={onToggleCollapse}
          className="rounded p-1 text-white/50 transition hover:bg-white/5 hover:text-white/80"
          aria-label={collapsed ? 'Expand run list' : 'Collapse run list'}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      {!collapsed && (
        <>
          <div className="flex flex-wrap gap-1.5 border-b border-white/[0.06] px-3 py-2">
            {(['all', 'react', 'plan_execute', 'plan_execute_synthesis'] as const).map((arm) => (
              <button
                key={arm}
                type="button"
                onClick={() => onArmFilter(arm)}
                className="rounded px-2 py-0.5 font-sans text-[10px] uppercase tracking-wide transition "
                style={{
                  background: armFilter === arm ? 'rgba(255,255,255,0.1)' : 'transparent',
                  color: arm === 'all' ? 'rgba(255,255,255,0.6)' : armTheme(arm as ArmName).color,
                  border: `1px solid ${armFilter === arm ? 'rgba(255,255,255,0.12)' : 'rgba(255,255,255,0.06)'}`,
                }}
              >
                {arm === 'all' ? 'All' : armTheme(arm as ArmName).label}
              </button>
            ))}
          </div>
          <div className="flex gap-1.5 px-3 py-2">
            {(['all', 'pass', 'fail'] as const).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => onPassFilter(f)}
                className="rounded px-2 py-0.5 font-sans text-[10px] uppercase tracking-wide text-white/60 transition "
                style={{
                  background: passFilter === f ? 'rgba(255,255,255,0.08)' : 'transparent',
                  border: '1px solid rgba(255,255,255,0.06)',
                }}
              >
                {f}
              </button>
            ))}
          </div>
        </>
      )}

      <div className="flex-1 overflow-y-auto">
        {filtered.map((run) => {
          const theme = armTheme(run.arm)
          const selected = run.run_id === selectedId
          return (
            <button
              key={run.run_id}
              type="button"
              onClick={() => onSelect(run.run_id)}
              className="flex w-full items-start gap-2 border-b border-white/[0.04] px-3 py-2.5 text-left transition "
              style={{
                background: selected ? 'rgba(255,255,255,0.04)' : 'transparent',
                boxShadow: selected ? `inset 2px 0 0 ${theme.color}` : undefined,
              }}
            >
              <StatusDot status={run.status} />
              {!collapsed && (
                <div className="min-w-0 flex-1">
                  <p className="truncate font-sans text-xs text-white/85">{run.task_name}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <span
                      className="rounded px-1.5 py-0.5 font-sans text-[10px]"
                      style={{ color: theme.color, background: theme.bg, border: `1px solid ${theme.border}` }}
                    >
                      {theme.label}
                    </span>
                    {run.duration_ms != null && (
                      <span className="font-mono text-[10px] text-white/40">{(run.duration_ms / 1000).toFixed(1)}s</span>
                    )}
                  </div>
                  <p className="mt-0.5 font-mono text-[10px] text-white/30">
                    {new Date(run.started_at).toLocaleString()}
                  </p>
                </div>
              )}
            </button>
          )
        })}
      </div>
    </motion.aside>
  )
}
