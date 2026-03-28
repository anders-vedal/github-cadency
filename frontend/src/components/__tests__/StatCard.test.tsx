import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatCard from '../StatCard'

describe('StatCard', () => {
  it('renders title and value', () => {
    render(<StatCard title="PRs Merged" value={42} />)
    expect(screen.getByText('PRs Merged')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('renders string value', () => {
    render(<StatCard title="Status" value="Active" />)
    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  it('renders subtitle when provided', () => {
    render(<StatCard title="Reviews" value={10} subtitle="this month" />)
    expect(screen.getByText('this month')).toBeInTheDocument()
  })

  it('does not render subtitle when not provided', () => {
    render(<StatCard title="Reviews" value={10} />)
    expect(screen.queryByText('this month')).not.toBeInTheDocument()
  })

  it('renders zero value', () => {
    render(<StatCard title="Open PRs" value={0} />)
    expect(screen.getByText('0')).toBeInTheDocument()
  })
})
