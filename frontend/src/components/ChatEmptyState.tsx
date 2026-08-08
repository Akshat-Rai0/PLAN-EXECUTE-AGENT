import { motion } from 'framer-motion'
import { Sparkles, Globe, FileSearch } from 'lucide-react'
import { useReducedMotion } from '../hooks/useAccessibility'
import { springEnter } from '../lib/motion'

const EXAMPLES = [
  {
    icon: FileSearch,
    label: 'Research a topic and summarize findings',
    task: 'Research the latest developments in AI agents and write a concise summary',
  },
  {
    icon: Globe,
    label: 'Browse the web to answer a question',
    task: 'Browse the web to find the current weather in Tokyo and report it',
  },
  {
    icon: Sparkles,
    label: 'Plan and execute a multi-step task',
    task: 'Create a plan to analyze a CSV file and generate insights',
  },
] as const

interface ChatEmptyStateProps {
  onSelectExample: (task: string) => void
}

export function ChatEmptyState({ onSelectExample }: ChatEmptyStateProps) {
  const reducedMotion = useReducedMotion()

  return (
    <div className="flex h-full flex-col items-center justify-center px-6 py-12">
      <motion.div
        initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
        animate={reducedMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
        transition={springEnter(reducedMotion)}
        className="mb-8 text-center"
      >
        <h2 className="font-sans text-lg font-semibold tracking-tight text-white/80">
          What should the agent work on?
        </h2>
        <p className="mt-2 max-w-sm text-sm text-white/40">
          Describe a task and watch the agent plan, call tools, and browse — live.
        </p>
      </motion.div>

      <div className="flex w-full max-w-md flex-col gap-2">
        {EXAMPLES.map((example, i) => {
          const Icon = example.icon
          return (
            <motion.button
              key={example.label}
              type="button"
              initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
              animate={reducedMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
              transition={{ ...springEnter(reducedMotion), delay: reducedMotion ? 0 : i * 0.08 }}
              whileHover={reducedMotion ? {} : { scale: 1.01, backgroundColor: 'rgba(255,255,255,0.06)' }}
              whileTap={reducedMotion ? {} : { scale: 0.98 }}
              onClick={() => onSelectExample(example.task)}
              className="flex items-center gap-3 rounded-lg border border-white/[0.08] bg-white/[0.02] px-4 py-3 text-left transition-colors hover:border-white/[0.12] focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500/60"
            >
              <Icon size={16} className="shrink-0 text-white/40" />
              <span className="text-sm text-white/70">{example.label}</span>
            </motion.button>
          )
        })}
      </div>
    </div>
  )
}
