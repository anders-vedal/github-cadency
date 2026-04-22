import { useState, useContext, useMemo, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { DateRangeContext, defaultFrom, defaultTo } from '@/hooks/useDateRange'
import { AuthContext, useAuthProvider } from '@/hooks/useAuth'
import { useIntegrations } from '@/hooks/useIntegrations'
import ErrorBoundary from '@/components/ErrorBoundary'
import Layout from '@/components/Layout'
import MetricsUsageBanner from '@/components/MetricsUsageBanner'
import SidebarLayout from '@/components/SidebarLayout'
import StatCardSkeleton from '@/components/StatCardSkeleton'
import Login from '@/pages/Login'
import AuthCallback from '@/pages/AuthCallback'
import type { SidebarItem, SidebarGroup } from '@/components/SidebarLayout'

// Lazy-loaded page components
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const TeamRegistry = lazy(() => import('@/pages/TeamRegistry'))
const DeveloperDetail = lazy(() => import('@/pages/DeveloperDetail'))
const Repos = lazy(() => import('@/pages/Repos'))
const SyncPage = lazy(() => import('@/pages/sync/SyncPage'))
const SyncDetailPage = lazy(() => import('@/pages/sync/SyncDetailPage'))
const AIAnalysis = lazy(() => import('@/pages/AIAnalysis'))
const AIWizard = lazy(() => import('@/pages/ai/AIWizard'))
const Goals = lazy(() => import('@/pages/Goals'))
const WorkloadOverview = lazy(() => import('@/pages/insights/WorkloadOverview'))
const CollaborationMatrix = lazy(() => import('@/pages/insights/CollaborationMatrix'))
const CollaborationPairPage = lazy(() => import('@/pages/insights/CollaborationPairPage'))
const Benchmarks = lazy(() => import('@/pages/insights/Benchmarks'))
const IssueQuality = lazy(() => import('@/pages/insights/IssueQuality'))
const CodeChurn = lazy(() => import('@/pages/insights/CodeChurn'))
const CIInsights = lazy(() => import('@/pages/insights/CIInsights'))
const DoraMetrics = lazy(() => import('@/pages/insights/DoraMetrics'))
const Investment = lazy(() => import('@/pages/insights/Investment'))
const InvestmentCategory = lazy(() => import('@/pages/insights/InvestmentCategory'))
const OrgChart = lazy(() => import('@/pages/insights/OrgChart'))
const IssueLinkage = lazy(() => import('@/pages/insights/IssueLinkage'))
const ExecutiveDashboard = lazy(() => import('@/pages/ExecutiveDashboard'))
const AISettingsPage = lazy(() => import('@/pages/settings/AISettings'))
const SlackSettingsPage = lazy(() => import('@/pages/settings/SlackSettings'))
const WorkCategoriesPage = lazy(() => import('@/pages/settings/WorkCategories'))
const NotificationSettings = lazy(() => import('@/pages/settings/NotificationSettings'))
const IntegrationSettings = lazy(() => import('@/pages/settings/IntegrationSettings'))
const AboutPage = lazy(() => import('@/pages/settings/About'))
const SprintDashboard = lazy(() => import('@/pages/insights/SprintDashboard'))
const PlanningInsights = lazy(() => import('@/pages/insights/PlanningInsights'))
const ProjectPortfolio = lazy(() => import('@/pages/insights/ProjectPortfolio'))
const IssueConversations = lazy(() => import('@/pages/insights/IssueConversations'))
const FlowAnalytics = lazy(() => import('@/pages/insights/FlowAnalytics'))
const Bottlenecks = lazy(() => import('@/pages/insights/Bottlenecks'))
const LinkageQuality = lazy(() => import('@/pages/admin/LinkageQuality'))
const MetricsGovernance = lazy(() => import('@/pages/admin/MetricsGovernance'))
const ClassifierRules = lazy(() => import('@/pages/admin/ClassifierRules'))

function PageSkeleton() {
  return (
    <div className="mx-auto max-w-7xl space-y-4 px-4 py-6">
      <StatCardSkeleton />
      <StatCardSkeleton />
    </div>
  )
}

const adminSidebarItems: SidebarItem[] = [
  { to: '/admin/team', label: 'Team' },
  { to: '/admin/repos', label: 'Repos' },
  { to: '/admin/sync', label: 'Sync' },
  { to: '/admin/ai', label: 'AI Analysis' },
  { to: '/admin/ai/settings', label: 'AI Settings' },
  { to: '/admin/slack', label: 'Slack' },
  { to: '/admin/work-categories', label: 'Work Categories' },
  { to: '/admin/integrations', label: 'Integrations' },
  { to: '/admin/linkage-quality', label: 'Linkage Quality' },
  { to: '/admin/metrics-governance', label: 'Metrics Governance' },
  { to: '/admin/classifier-rules', label: 'Classifier Rules' },
  { to: '/admin/notifications', label: 'Notifications' },
  { to: '/admin/about', label: 'About' },
]

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('devpulse_token')
  const auth = useContext(AuthContext)
  if (!token) {
    return <Navigate to="/login" replace />
  }
  if (auth?.isLoading) {
    return null
  }
  // Token exists but user failed to load (e.g., deleted from DB) — redirect to login
  if (!auth?.user) {
    localStorage.removeItem('devpulse_token')
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

function AppRoutes() {
  const [dateFrom, setDateFrom] = useState(defaultFrom)
  const [dateTo, setDateTo] = useState(defaultTo)
  const auth = useAuthProvider()
  const { data: integrations } = useIntegrations()
  const hasLinear = integrations?.some((i) => i.type === 'linear' && i.status === 'active')

  const insightsSidebarGroups = useMemo<SidebarGroup[]>(() => {
    const issuesItems: SidebarItem[] = [
      { to: '/insights/issue-quality', label: 'Issue Quality' },
      { to: '/insights/issue-linkage', label: 'Issue Linkage' },
    ]
    if (hasLinear) {
      issuesItems.push({ to: '/insights/conversations', label: 'Conversations' })
    }
    const planningGroup: SidebarGroup = hasLinear
      ? {
          label: 'Planning',
          items: [
            { to: '/insights/sprints', label: 'Sprints' },
            { to: '/insights/planning', label: 'Planning Health' },
            { to: '/insights/projects', label: 'Projects' },
            { to: '/insights/flow', label: 'Flow Analytics' },
            { to: '/insights/bottlenecks', label: 'Bottlenecks' },
          ],
        }
      : {
          label: 'Planning',
          items: [{ to: '/admin/integrations', label: 'Sprint Planning ›' }],
        }
    return [
      {
        label: 'People',
        items: [
          { to: '/insights/workload', label: 'Workload' },
          { to: '/insights/collaboration', label: 'Collaboration' },
          { to: '/insights/benchmarks', label: 'Benchmarks' },
          { to: '/insights/org-chart', label: 'Org Chart' },
        ],
      },
      {
        label: 'Delivery',
        items: [
          { to: '/insights/dora', label: 'DORA Metrics' },
          { to: '/insights/cicd', label: 'CI/CD' },
          { to: '/insights/code-churn', label: 'Code Churn' },
          { to: '/insights/investment', label: 'Investment' },
        ],
      },
      { label: 'Issues', items: issuesItems },
      planningGroup,
    ]
  }, [hasLinear])

  return (
    <AuthContext value={auth}>
      <DateRangeContext value={{ dateFrom, dateTo, setDateFrom, setDateTo }}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <Layout>
                  <Suspense fallback={<PageSkeleton />}>
                  <ErrorBoundary>
                    <Routes>
                      <Route path="/" element={<ErrorBoundary>{auth.isAdmin ? <Dashboard /> : <Navigate to={`/team/${auth.user?.developer_id}`} replace />}</ErrorBoundary>} />
                      <Route path="/executive" element={auth.isAdmin ? <ErrorBoundary><ExecutiveDashboard /></ErrorBoundary> : <Navigate to="/" replace />} />
                      <Route path="/team" element={<Navigate to="/admin/team" replace />} />
                      <Route path="/team/:id" element={<ErrorBoundary><DeveloperDetail /></ErrorBoundary>} />
                      <Route path="/goals" element={<ErrorBoundary><Goals /></ErrorBoundary>} />

                      {/* Insights — sidebar layout */}
                      <Route path="/insights/*" element={
                        auth.isAdmin ? (
                          <SidebarLayout groups={insightsSidebarGroups} title="Insights">
                            <ErrorBoundary>
                              <MetricsUsageBanner className="mb-4" />
                              <Routes>
                                <Route path="/workload" element={<WorkloadOverview />} />
                                <Route path="/collaboration" element={<CollaborationMatrix />} />
                                <Route path="/collaboration/:reviewerId/:authorId" element={<CollaborationPairPage />} />
                                <Route path="/benchmarks" element={<Benchmarks />} />
                                <Route path="/issue-quality" element={<IssueQuality />} />
                                <Route path="/issue-linkage" element={<IssueLinkage />} />
                                <Route path="/code-churn" element={<CodeChurn />} />
                                <Route path="/cicd" element={<CIInsights />} />
                                <Route path="/dora" element={<DoraMetrics />} />
                                <Route path="/investment" element={<Investment />} />
                                <Route path="/investment/:category" element={<InvestmentCategory />} />
                                <Route path="/org-chart" element={<OrgChart />} />
                                <Route path="/sprints" element={<SprintDashboard />} />
                                <Route path="/planning" element={<PlanningInsights />} />
                                <Route path="/projects" element={<ProjectPortfolio />} />
                                <Route path="/conversations" element={<IssueConversations />} />
                                <Route path="/flow" element={<FlowAnalytics />} />
                                <Route path="/bottlenecks" element={<Bottlenecks />} />
                                <Route path="*" element={<Navigate to="/insights/workload" replace />} />
                              </Routes>
                            </ErrorBoundary>
                          </SidebarLayout>
                        ) : <Navigate to="/" replace />
                      } />

                      {/* Admin — sidebar layout */}
                      <Route path="/admin/*" element={
                        auth.isAdmin ? (
                          <SidebarLayout items={adminSidebarItems} title="Admin">
                            <ErrorBoundary>
                              <Routes>
                                <Route path="/team" element={<TeamRegistry />} />
                                <Route path="/repos" element={<Repos />} />
                                <Route path="/sync" element={<SyncPage />} />
                                <Route path="/sync/:id" element={<SyncDetailPage />} />
                                <Route path="/ai" element={<AIAnalysis />} />
                                <Route path="/ai/new" element={<AIWizard />} />
                                <Route path="/ai/settings" element={<AISettingsPage />} />
                                <Route path="/slack" element={<SlackSettingsPage />} />
                                <Route path="/work-categories" element={<WorkCategoriesPage />} />
                                <Route path="/integrations" element={<IntegrationSettings />} />
                                <Route path="/linkage-quality" element={<LinkageQuality />} />
                                <Route path="/metrics-governance" element={<MetricsGovernance />} />
                                <Route path="/classifier-rules" element={<ClassifierRules />} />
                                <Route path="/notifications" element={<NotificationSettings />} />
                                <Route path="/about" element={<AboutPage />} />
                                <Route path="*" element={<Navigate to="/admin/team" replace />} />
                              </Routes>
                            </ErrorBoundary>
                          </SidebarLayout>
                        ) : <Navigate to="/" replace />
                      } />
                    </Routes>
                  </ErrorBoundary>
                  </Suspense>
                </Layout>
              </ProtectedRoute>
            }
          />
        </Routes>
      </DateRangeContext>
    </AuthContext>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
        <Toaster position="bottom-right" richColors duration={4000} />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
