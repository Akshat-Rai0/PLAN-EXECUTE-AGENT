import { useState } from 'react'
import { Send } from 'lucide-react'
import { motion } from 'framer-motion'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
  isWaitingForInput?: boolean
}

export function ChatInput({ onSend, disabled, isWaitingForInput }: ChatInputProps) {
  const [input, setInput] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (input.trim() && !disabled) {
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
      <div
        className="flex gap-2 rounded-lg transition-all duration-300"
        style={{
          animation: isWaitingForInput ? 'border-pulse 2s infinite' : 'none',
          boxShadow: isWaitingForInput ? '0 0 12px rgba(245, 158, 11, 0.3)' : 'none',
          border: isWaitingForInput ? '1px solid rgba(245, 158, 11, 0.8)' : '1px solid transparent',
          padding: isWaitingForInput ? '2px' : '0',
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={isWaitingForInput ? "Please respond to the prompt above ↑" : "Enter your task..."}
          disabled={isActuallyDisabled}
          className="flex-1 rounded border border-white/[0.06] bg-white/[0.02] px-4 py-2.5 text-sm text-white placeholder-white/30 outline-none transition-all focus:border-blue-500 disabled:opacity-40"
        />
        <motion.button
          type="submit"
          disabled={isActuallyDisabled || !input.trim()}
          whileTap={isActuallyDisabled || !input.trim() ? {} : { scale: 0.95 }}
          className="flex items-center gap-2 rounded bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:bg-white/10 disabled:text-white/30"
        >
          {isWaitingForInput ? 'Respond Above' : <Send size={16} />}
        </motion.button>
      </div>
    </form>
  )
}
