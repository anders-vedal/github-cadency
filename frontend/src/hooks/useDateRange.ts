import { createContext, useContext } from 'react'

export interface DateRange {
  dateFrom: string
  dateTo: string
  setDateFrom: (v: string) => void
  setDateTo: (v: string) => void
}

function defaultFrom() {
  const d = new Date()
  d.setDate(d.getDate() - 30)
  return d.toISOString().slice(0, 10)
}

function defaultTo() {
  return new Date().toISOString().slice(0, 10)
}

export const DateRangeContext = createContext<DateRange>({
  dateFrom: defaultFrom(),
  dateTo: defaultTo(),
  setDateFrom: () => {},
  setDateTo: () => {},
})

export function useDateRange() {
  return useContext(DateRangeContext)
}

export { defaultFrom, defaultTo }
