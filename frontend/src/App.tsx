import { useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DateRangeContext, defaultFrom, defaultTo } from '@/hooks/useDateRange'
import Layout from '@/components/Layout'
import Dashboard from '@/pages/Dashboard'
import TeamRegistry from '@/pages/TeamRegistry'
import DeveloperDetail from '@/pages/DeveloperDetail'
import Repos from '@/pages/Repos'
import SyncStatus from '@/pages/SyncStatus'
import AIAnalysis from '@/pages/AIAnalysis'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

export default function App() {
  const [dateFrom, setDateFrom] = useState(defaultFrom)
  const [dateTo, setDateTo] = useState(defaultTo)

  return (
    <QueryClientProvider client={queryClient}>
      <DateRangeContext value={{ dateFrom, dateTo, setDateFrom, setDateTo }}>
        <BrowserRouter>
          <Layout>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/team" element={<TeamRegistry />} />
              <Route path="/team/:id" element={<DeveloperDetail />} />
              <Route path="/repos" element={<Repos />} />
              <Route path="/sync" element={<SyncStatus />} />
              <Route path="/ai" element={<AIAnalysis />} />
            </Routes>
          </Layout>
        </BrowserRouter>
      </DateRangeContext>
    </QueryClientProvider>
  )
}
