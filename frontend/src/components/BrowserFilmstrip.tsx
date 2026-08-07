interface BrowserFilmstripProps {
  screenshotUrl: string
  title?: string
}

export function BrowserFilmstrip({ screenshotUrl, title }: BrowserFilmstripProps) {
  return (
    <div className="mt-2 overflow-hidden rounded border border-white/[0.08]">
      <div className="border-b border-white/[0.06] bg-white/[0.03] px-2 py-1 font-mono text-[10px] text-white/40">
        {title ?? 'Browser screenshot'}
      </div>
      <img
        src={screenshotUrl}
        alt={title ?? 'Browser step screenshot'}
        className="max-h-48 w-full object-cover object-top"
        loading="lazy"
      />
    </div>
  )
}
