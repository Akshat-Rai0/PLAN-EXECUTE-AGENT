import { useState } from 'react'
import { Send, Clock, Brain } from 'lucide-react'
import { motion } from 'framer-motion'
import { useReducedMotion } from '../hooks/useAccessibility'
import type { ArmName } from '../lib/types'
import { armTheme } from '../lib/armTheme'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
  isWaitingForInput?: boolean
  isThinking?: boolean
  thinkingArm?: ArmName
}

export function ChatInput({ onSend, disabled, isWaitingForInput, isThinking, thinkingArm = 'plan_execute_synthesis' }: ChatInputProps) {
  const [input, setInput] = useState('')
  const reducedMotion = useReducedMotion()
  const theme = armTheme(thinkingArm)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (input.trim() && !disabled && !isWaitingForInput) {
      onSend(input.trim())
      setInput('')
    }
  }

  const isActuallyDisabled = disabled || isWaitingForInput

  return (
    <form
      onSubmit={handleSubmit}
      className="p-4 transition-colors duration-300"
      style={{
        borderTop: '1px solid rgba(255,255,255,0.06)',
        backgroundColor: isWaitingForInput ? 'rgba(245, 158, 11, 0.03)' : 'transparent',
      }}
    >
      {isWaitingForInput && (
        <p className="mb-2 flex items-center gap-1.5 text-xs text-amber-300/80">
          <Clock size={12} />
          Waiting for your response above
        </p>
      )}
      {isThinking && !isWaitingForInput && (
        <motion.div
          initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -5 }}
          animate={reducedMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
          className="mb-2 flex items-center gap-2"
        >
          <motion.div
            animate={reducedMotion ? {} : { scale: [1, 1.15, 1], opacity: [0.7, 1, 0.7] }}
            transition={reducedMotion ? {} : { duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
          >
            <Brain size={12} style={{ color: theme.color }} />
          </motion.div>
          <div className="flex gap-1">
            <motion.div
              className="h-1 w-1 rounded-full"
              style={{ backgroundColor: theme.color }}
              animate={reducedMotion ? {} : { opacity: [0.3, 1, 0.3], scale: [0.8, 1.2, 0.8] }}
              transition={reducedMotion ? {} : { duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
            />
            <motion.div
              className="h-1 w-1 rounded-full"
              style={{ backgroundColor: theme.color }}
              animate={reducedMotion ? {} : { opacity: [0.3, 1, 0.3], scale: [0.8, 1.2, 0.8] }}
              transition={reducedMotion ? {} : { duration: 1.5, repeat: Infinity, ease: 'easeInOut', delay: 0.15 }}
            />
            <motion.div
              className="h-1 w-1 rounded-full"
              style={{ backgroundColor: theme.color }}
              animate={reducedMotion ? {} : { opacity: [0.3, 1, 0.3], scale: [0.8, 1.2, 0.8] }}
              transition={reducedMotion ? {} : { duration: 1.5, repeat: Infinity, ease: 'easeInOut', delay: 0.3 }}
            />
          </div>
          <span className="text-xs text-white/70">Thinking…</span>
        </motion.div>
      )}
      <div
        className="flex gap-2 rounded-lg transition-all duration-300"
        style={{
          animation: isWaitingForInput && !reducedMotion ? 'border-pulse 2s infinite' : 'none',
          boxShadow: isWaitingForInput ? '0 0 12px rgba(245, 158, 11, 0.3)' : 'none',
          border: isWaitingForInput ? '1px solid rgba(245, 158, 11, 0.8)' : '1px solid transparent',
          padding: isWaitingForInput ? '2px' : '0',
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={isWaitingForInput ? 'Please respond to the prompt above ↑' : 'Enter your task...'}
          disabled={isActuallyDisabled}
          className="flex-1 rounded border border-white/[0.06] bg-white/[0.02] px-4 py-2.5 text-sm text-white placeholder-white/30 outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30 disabled:opacity-40"
        />
        <motion.button
          type="submit"
          disabled={isActuallyDisabled || !input.trim()}
          whileHover={isActuallyDisabled || !input.trim() ? {} : { opacity: 0.9 }}
          whileTap={isActuallyDisabled || !input.trim() ? {} : { scale: 0.96 }}
          transition={{ duration: 0.1 }}
          className="flex items-center gap-2 rounded bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500/50 disabled:bg-white/10 disabled:text-white/30"
        >
          {isWaitingForInput ? 'Respond Above' : <Send size={16} />}
        </motion.button>
      </div>
    </form>
  )
}
