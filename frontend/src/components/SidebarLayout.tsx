import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

export interface SidebarItem {
  to: string
  label: string
  icon?: ReactNode
}

export interface SidebarGroup {
  label: string
  items: SidebarItem[]
}

interface SidebarLayoutProps {
  title: string
  children: ReactNode
  items?: SidebarItem[]
  groups?: SidebarGroup[]
}

export default function SidebarLayout({ title, children, items, groups }: SidebarLayoutProps) {
  const { pathname } = useLocation()

  const renderItem = (item: SidebarItem) => {
    const isActive = pathname === item.to || pathname.startsWith(item.to + '/')
    return (
      <Link
        key={item.to}
        to={item.to}
        className={cn(
          'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors',
          isActive
            ? 'bg-muted text-foreground'
            : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'
        )}
      >
        {item.icon}
        {item.label}
      </Link>
    )
  }

  return (
    <div className="flex gap-6">
      <nav className="sticky top-20 max-h-[calc(100vh-5rem)] w-48 shrink-0 space-y-1 overflow-y-auto pb-4">
        <h2 className="mb-3 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {title}
        </h2>
        {groups
          ? groups.map((group, idx) => (
              <section key={group.label} className="space-y-1">
                <h3
                  className={cn(
                    'mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70',
                    idx === 0 ? 'mt-0' : 'mt-5'
                  )}
                >
                  {group.label}
                </h3>
                {group.items.map(renderItem)}
              </section>
            ))
          : items?.map(renderItem)}
      </nav>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}
