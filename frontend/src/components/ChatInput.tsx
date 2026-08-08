import { useState } from 'react'
import { Send, Clock } from 'lucide-react'
import { motion } from 'framer-motion'
import { useReducedMotion } from '../hooks/useAccessibility'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
  isWaitingForInput?: boolean
}

export function ChatInput({ onSend, disabled, isWaitingForInput }: ChatInputProps) {
  const [input, setInput] = useState('')
  const reducedMotion = useReducedMotion()

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
