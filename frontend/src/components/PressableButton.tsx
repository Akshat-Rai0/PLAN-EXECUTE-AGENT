import { motion } from 'framer-motion'
import type { HTMLMotionProps } from 'framer-motion'
import type { ReactNode } from 'react'
import { useReducedMotion } from '../hooks/useAccessibility'

interface PressableButtonProps extends HTMLMotionProps<'button'> {
  children: ReactNode
  variant?: 'primary' | 'success' | 'danger' | 'ghost'
  accentColor?: string
}

const VARIANTS = {
  primary: 'bg-blue-600 text-white hover:bg-blue-500 active:bg-blue-700',
  success: 'bg-green-600 text-white hover:bg-green-500 active:bg-green-700',
  danger: 'bg-red-600 text-white hover:bg-red-500 active:bg-red-700',
  ghost: 'bg-white/[0.06] text-white/80 hover:bg-white/[0.1] active:bg-white/[0.04]',
}

export function PressableButton({
  children,
  variant = 'primary',
  accentColor,
  className = '',
  disabled,
  ...props
}: PressableButtonProps) {
  const reducedMotion = useReducedMotion()

  return (
    <motion.button
      type="button"
      disabled={disabled}
      whileHover={disabled || reducedMotion ? {} : { opacity: 0.92 }}
      whileTap={disabled || reducedMotion ? {} : { scale: 0.96 }}
      transition={{ duration: 0.1 }}
      className={`rounded px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-40 ${VARIANTS[variant]} ${className}`}
      style={
        accentColor
          ? ({
              '--tw-ring-color': accentColor,
              outlineColor: accentColor,
            } as React.CSSProperties)
          : undefined
      }
      {...props}
    >
      {children}
    </motion.button>
  )
}
