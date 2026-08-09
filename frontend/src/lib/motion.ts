import { useReducedMotion, useReducedTransparency } from '../hooks/useAccessibility'

export { useReducedMotion, useReducedTransparency }

export const SPRING_PANEL = { type: 'spring' as const, damping: 50, stiffness: 380, mass: 0.8 }
export const SPRING_SCRUBBER = { type: 'spring' as const, damping: 50, stiffness: 400, mass: 0.6 }
export const SPRING_STEP = { type: 'spring' as const, damping: 50, stiffness: 420, mass: 0.7 }
export const SPRING_ENTER = { type: 'spring' as const, damping: 50, stiffness: 350, mass: 1 }
export const SPRING_INTERRUPT = { type: 'spring' as const, damping: 50, stiffness: 300, mass: 1.2 }
export const SPRING_PRESS = { type: 'spring' as const, damping: 50, stiffness: 500, mass: 0.5 }
export const SPRING_STREAM_CARD = { type: 'spring' as const, damping: 50, stiffness: 380, mass: 0.9 }

export function springPanel(reduced: boolean) {
  return reduced ? { duration: 0.18 } : SPRING_PANEL
}

export function springScrubber(reduced: boolean) {
  return reduced ? { duration: 0.18 } : SPRING_SCRUBBER
}

export function springStep(reduced: boolean) {
  return reduced ? { duration: 0.18 } : SPRING_STEP
}

export function springEnter(reduced: boolean) {
  return reduced ? { duration: 0.18 } : SPRING_ENTER
}

export function springInterrupt(reduced: boolean) {
  return reduced ? { duration: 0.18 } : SPRING_INTERRUPT
}

export function springPress(reduced: boolean) {
  return reduced ? { duration: 0.08 } : SPRING_PRESS
}

export function springStreamCard(reduced: boolean) {
  return reduced ? { duration: 0.18 } : SPRING_STREAM_CARD
}
