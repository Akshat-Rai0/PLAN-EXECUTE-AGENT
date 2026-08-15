import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import type { ArmName, ChatMessage as ChatMessageType } from '../lib/types'
import { armTheme } from '../lib/armTheme'
import { useReducedMotion } from '../hooks/useAccessibility'
import { springEnter } from '../lib/motion'

interface ChatMessageProps {
  message: ChatMessageType
  arm?: ArmName
  isStreaming?: boolean
}


export function ChatMessage({ message, arm = 'plan_execute_synthesis', isStreaming = false }: ChatMessageProps) {
  const reducedMotion = useReducedMotion()
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'
  const theme = armTheme(arm)

  return (
    <motion.div
      layout
      initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
      animate={reducedMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
      transition={springEnter(reducedMotion)}
      className={`mb-4 flex ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div
        className={`max-w-[85%] rounded-xl px-4 py-3 ${
          isUser
            ? 'bg-blue-600 text-white'
            : isSystem
              ? 'bg-white/[0.04] text-xs text-white/50 border border-white/[0.06]'
              : 'bg-white/[0.02] border border-white/[0.06] text-white/90'
        }`}
        style={!isUser && !isSystem ? { borderLeft: `3px solid ${theme.color}` } : undefined}
      >
        {!isSystem && (
          <div className="mb-1 text-[10px] font-medium uppercase tracking-wide opacity-50">
            {isUser ? 'You' : 'Assistant'}
          </div>
        )}
        <div className="whitespace-pre-wrap break-words text-[13px] leading-relaxed">
          {message.content}
        </div>
      </div>
    </motion.div>
  )
}
