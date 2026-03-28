import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useDateRange } from '@/hooks/useDateRange'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/', label: 'Dashboard' },
  { to: '/team', label: 'Team' },
  { to: '/repos', label: 'Repos' },
  { to: '/sync', label: 'Sync' },
  { to: '/ai', label: 'AI Analysis' },
]

export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation()
  const { dateFrom, dateTo, setDateFrom, setDateTo } = useDateRange()

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            DevPulse
          </Link>
          <nav className="flex items-center gap-1">
            {navItems.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  location.pathname === item.to
                    ? 'bg-muted text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2 text-sm">
            <label className="text-muted-foreground">From</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="rounded-md border bg-background px-2 py-1 text-sm"
            />
            <label className="text-muted-foreground">To</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="rounded-md border bg-background px-2 py-1 text-sm"
            />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  )
}
