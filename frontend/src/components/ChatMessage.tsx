import type { ChatMessage } from '../lib/types'

interface ChatMessageProps {
  message: ChatMessage
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 ${
          isUser
            ? 'bg-blue-600 text-white'
            : isSystem
            ? 'bg-gray-700 text-gray-300 text-xs'
            : 'bg-gray-800 text-gray-100'
        }`}
      >
        {!isSystem && (
          <div className="mb-1 text-xs opacity-70">
            {isUser ? 'You' : 'Assistant'}
          </div>
        )}
        <div className="whitespace-pre-wrap break-words">{message.content}</div>
      </div>
    </div>
  )
}
