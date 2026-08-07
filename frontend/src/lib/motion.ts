import { useReducedMotion, useReducedTransparency } from '../hooks/useAccessibility'

export { useReducedMotion, useReducedTransparency }

export const SPRING_PANEL = { type: 'spring' as const, damping: 1, stiffness: 380, mass: 0.8 }
export const SPRING_SCRUBBER = { type: 'spring' as const, damping: 1, stiffness: 400, mass: 0.6 }
export const SPRING_STEP = { type: 'spring' as const, damping: 1, stiffness: 420, mass: 0.7 }

export function springPanel(reduced: boolean) {
  return reduced ? { duration: 0.18 } : SPRING_PANEL
}

export function springScrubber(reduced: boolean) {
  return reduced ? { duration: 0.18 } : SPRING_SCRUBBER
}

export function springStep(reduced: boolean) {
  return reduced ? { duration: 0.18 } : SPRING_STEP
}
