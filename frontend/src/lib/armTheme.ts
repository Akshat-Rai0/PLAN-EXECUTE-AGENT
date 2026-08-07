import type { ArmName } from './types'

export interface ArmTheme {
  label: string
  color: string
  glow: string
  border: string
  bg: string
}

export const ARM_THEMES: Record<ArmName, ArmTheme> = {
  react: {
    label: 'ReAct',
    color: '#22d3ee',
    glow: 'rgba(34, 211, 238, 0.35)',
    border: 'rgba(34, 211, 238, 0.35)',
    bg: 'rgba(34, 211, 238, 0.12)',
  },
  plan_execute: {
    label: 'Plan & Execute',
    color: '#a78bfa',
    glow: 'rgba(167, 139, 250, 0.35)',
    border: 'rgba(167, 139, 250, 0.35)',
    bg: 'rgba(167, 139, 250, 0.12)',
  },
  plan_execute_synthesis: {
    label: 'P&E + Synthesis',
    color: '#fbbf24',
    glow: 'rgba(251, 191, 36, 0.35)',
    border: 'rgba(251, 191, 36, 0.35)',
    bg: 'rgba(251, 191, 36, 0.12)',
  },
}

export function armTheme(arm: ArmName): ArmTheme {
  return ARM_THEMES[arm]
}
