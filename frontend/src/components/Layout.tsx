import { useState, useRef, useEffect, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useDateRange } from '@/hooks/useDateRange'
import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import DateRangePicker from '@/components/DateRangePicker'

interface NavItem {
  to: string
  label: string
}

interface NavGroup {
  label: string
  children: NavItem[]
}

type NavEntry = NavItem | NavGroup

function isGroup(entry: NavEntry): entry is NavGroup {
  return 'children' in entry
}

const adminNavItems: NavEntry[] = [
  { to: '/', label: 'Dashboard' },
  { to: '/team', label: 'Team' },
  {
    label: 'Insights',
    children: [
      { to: '/insights/workload', label: 'Workload' },
      { to: '/insights/collaboration', label: 'Collaboration' },
      { to: '/insights/benchmarks', label: 'Benchmarks' },
      { to: '/insights/issue-quality', label: 'Issue Quality' },
      { to: '/insights/code-churn', label: 'Code Churn' },
      { to: '/insights/cicd', label: 'CI/CD' },
      { to: '/insights/dora', label: 'DORA Metrics' },
      { to: '/insights/investment', label: 'Investment' },
    ],
  },
  { to: '/repos', label: 'Repos' },
  { to: '/sync', label: 'Sync' },
  { to: '/ai', label: 'AI Analysis' },
  { to: '/settings/ai', label: 'AI Settings' },
  { to: '/goals', label: 'Goals' },
  { to: '/executive', label: 'Executive' },
]

function NavDropdown({ group, pathname }: { group: NavGroup; pathname: string }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const isActive = group.children.some((c) => pathname === c.to || pathname.startsWith(c.to + '/'))

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          'rounded-md px-3 py-1.5 text-sm font-medium transition-colors inline-flex items-center gap-1',
          isActive
            ? 'bg-muted text-foreground'
            : 'text-muted-foreground hover:text-foreground'
        )}
      >
        {group.label}
        <svg
          className={cn('h-3 w-3 transition-transform', open && 'rotate-180')}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 min-w-[160px] rounded-lg border bg-popover p-1 shadow-md z-50">
          {group.children.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              onClick={() => setOpen(false)}
              className={cn(
                'block rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                pathname === item.to
                  ? 'bg-muted text-foreground'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              )}
            >
              {item.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation()
  const { dateFrom, dateTo, setDateFrom, setDateTo } = useDateRange()
  const { user, isAdmin, logout } = useAuth()

  const navItems: NavEntry[] = isAdmin
    ? adminNavItems
    : [
        { to: `/team/${user?.developer_id}`, label: 'My Stats' },
        { to: '/goals', label: 'My Goals' },
      ]

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            DevPulse
          </Link>
          <nav className="flex items-center gap-1">
            {navItems.map((entry) =>
              isGroup(entry) ? (
                <NavDropdown key={entry.label} group={entry} pathname={location.pathname} />
              ) : (
                <Link
                  key={entry.to}
                  to={entry.to}
                  className={cn(
                    'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                    location.pathname === entry.to
                      ? 'bg-muted text-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                >
                  {entry.label}
                </Link>
              )
            )}
          </nav>
          <div className="ml-auto flex items-center gap-2 text-sm">
            <DateRangePicker
              dateFrom={dateFrom}
              dateTo={dateTo}
              onDateFromChange={setDateFrom}
              onDateToChange={setDateTo}
            />
            {user && (
              <>
                <span className="text-muted-foreground">
                  {user.display_name}
                </span>
                <Button variant="ghost" size="sm" onClick={logout}>
                  Logout
                </Button>
              </>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  )
}
