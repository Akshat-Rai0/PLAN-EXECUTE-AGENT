import { useEffect, useState } from 'react'

export function useReducedMotion(): boolean {
  // Always return true to disable all animations/bouncing effects
  return true
}

export function useReducedTransparency(): boolean {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-transparency: reduce)')
    setReduced(mq.matches)
    const handler = () => setReduced(mq.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return reduced
}
