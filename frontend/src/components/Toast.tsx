import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Check, Info, AlertTriangle, X } from 'lucide-react'
import { springEnter } from '../lib/motion'
import { useReducedMotion } from '../hooks/useAccessibility'

type ToastType = 'success' | 'info' | 'error'

interface ToastMessage {
  id: string
  message: string
  type: ToastType
}

// Global toast state manager
let addToastListener: ((toast: ToastMessage) => void) | null = null

export function toast(message: string, type: ToastType = 'info') {
  if (addToastListener) {
    addToastListener({ id: Math.random().toString(36).substring(2, 9), message, type })
  }
}

export function ToastProvider() {
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  const reducedMotion = useReducedMotion()

  useEffect(() => {
    addToastListener = (toast) => {
      setToasts((prev) => [...prev, toast])
    }
    return () => {
      addToastListener = null
    }
  }, [])

  useEffect(() => {
    if (toasts.length > 0) {
      const timer = setTimeout(() => {
        setToasts((prev) => prev.slice(1))
      }, 3000)
      return () => clearTimeout(timer)
    }
  }, [toasts])

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      <AnimatePresence>
        {toasts.map((t) => {
          const isError = t.type === 'error'
          const isSuccess = t.type === 'success'
          const Icon = isError ? AlertTriangle : isSuccess ? Check : Info
          const colorClass = isError
            ? 'text-red-400 bg-red-500/10 border-red-500/30'
            : isSuccess
              ? 'text-green-400 bg-green-500/10 border-green-500/30'
              : 'text-blue-400 bg-blue-500/10 border-blue-500/30'

          return (
            <motion.div
              key={t.id}
              layout
              initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 20, scale: 0.95 }}
              animate={reducedMotion ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
              exit={reducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.95, transition: { duration: 0.1 } }}
              transition={springEnter(reducedMotion)}
              className={`flex items-center gap-3 rounded-lg border p-3 shadow-lg backdrop-blur-md ${colorClass}`}
            >
              <Icon size={18} />
              <span className="font-sans text-sm font-medium text-white/90">{t.message}</span>
              <button
                type="button"
                className="ml-2 rounded-full p-1 opacity-50 transition-opacity hover:opacity-100"
                onClick={() => setToasts((prev) => prev.filter((item) => item.id !== t.id))}
              >
                <X size={14} />
              </button>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
