import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { MessageSquare, Swords, Smile, Users, HeartPulse } from 'lucide-react'
import type { AnalysisWizardType } from '@/utils/types'

interface StepChooseTypeProps {
  selected: AnalysisWizardType | null
  onSelect: (type: AnalysisWizardType) => void
}

const analysisTypes: {
  type: AnalysisWizardType
  icon: typeof MessageSquare
  title: string
  scopeBadge: string
  description: string
  reads: string
  generates: string
}[] = [
  {
    type: 'communication',
    icon: MessageSquare,
    title: 'Communication Analysis',
    scopeBadge: 'Per Developer',
    description:
      'Evaluates clarity, constructiveness, responsiveness, and tone across a developer\'s PR descriptions, review comments, and issue comments.',
    reads:
      'PR descriptions (up to 50), review comments (up to 50), issue comments (up to 50) — each truncated to 500 characters',
    generates:
      'Scores (1-10) for clarity, constructiveness, responsiveness, and tone, plus qualitative observations and actionable recommendations',
  },
  {
    type: 'conflict',
    icon: Swords,
    title: 'Conflict Detection',
    scopeBadge: 'Per Team',
    description:
      'Analyzes team code review interactions to identify friction patterns, especially around CHANGES_REQUESTED reviews and recurring disagreements between pairs.',
    reads:
      'Up to 50 review comments between team members, with reviewer/author attribution and review state',
    generates:
      'Conflict score (1-10), specific friction pairs with patterns, recurring issues, and de-escalation recommendations',
  },
  {
    type: 'sentiment',
    icon: Smile,
    title: 'Sentiment Analysis',
    scopeBadge: 'Developer / Team / Repo',
    description:
      'Lightweight analysis of overall tone and morale across comments and PR descriptions in the selected scope.',
    reads:
      'Review comments and issue comments (up to 50 each) from the selected scope',
    generates:
      'Sentiment score (1-10), trend direction (improving/stable/declining), and notable patterns',
  },
  {
    type: 'one_on_one_prep',
    icon: Users,
    title: '1:1 Prep Brief',
    scopeBadge: 'Per Developer',
    description:
      'Generates a structured meeting brief for engineering managers. Combines activity metrics, trends, peer benchmarks, goal progress, and review quality into actionable talking points.',
    reads:
      'Developer stats, 4-week trends, team benchmarks, recent PRs (up to 30), review quality tiers, active goals with progress, previous brief (for continuity), issue creator stats vs team averages',
    generates:
      'Period summary, metrics highlights with concern levels, notable work, suggested talking points with constructive framing, and goal progress',
  },
  {
    type: 'team_health',
    icon: HeartPulse,
    title: 'Team Health Check',
    scopeBadge: 'Per Team / All',
    description:
      'Comprehensive team health assessment combining velocity, workload balance, collaboration patterns, communication flags, and goal progress into a prioritized action plan.',
    reads:
      'Team stats + benchmarks, per-developer workload scores, collaboration matrix + insights, CHANGES_REQUESTED reviews with body text (up to 60), heated issue threads (3+ back-and-forth comments), team goal progress',
    generates:
      'Health score (1-10), velocity assessment, workload concerns with suggestions, collaboration patterns, communication flags with severity, process recommendations, strengths, and prioritized action items',
  },
]

export default function StepChooseType({ selected, onSelect }: StepChooseTypeProps) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Choose Analysis Type</h2>
        <p className="text-sm text-muted-foreground">
          Select the type of AI analysis you want to run. Each card explains what data is read and what the analysis generates.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {analysisTypes.slice(0, 3).map(({ type, icon: Icon, title, scopeBadge, description, reads, generates }) => (
          <Card
            key={type}
            className={cn(
              'cursor-pointer transition-all',
              selected === type ? 'ring-2 ring-primary' : 'hover:ring-2 hover:ring-primary/50',
            )}
            onClick={() => onSelect(type)}
          >
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Icon className="h-4 w-4 text-primary" />
                {title}
              </CardTitle>
              <Badge variant="secondary" className="w-fit text-xs">{scopeBadge}</Badge>
              <CardDescription className="text-xs">{description}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <div>
                <span className="font-medium text-muted-foreground">Reads: </span>
                {reads}
              </div>
              <div>
                <span className="font-medium text-muted-foreground">Generates: </span>
                {generates}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {analysisTypes.slice(3).map(({ type, icon: Icon, title, scopeBadge, description, reads, generates }) => (
          <Card
            key={type}
            className={cn(
              'cursor-pointer transition-all',
              selected === type ? 'ring-2 ring-primary' : 'hover:ring-2 hover:ring-primary/50',
            )}
            onClick={() => onSelect(type)}
          >
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Icon className="h-4 w-4 text-primary" />
                {title}
              </CardTitle>
              <Badge variant="secondary" className="w-fit text-xs">{scopeBadge}</Badge>
              <CardDescription className="text-xs">{description}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <div>
                <span className="font-medium text-muted-foreground">Reads: </span>
                {reads}
              </div>
              <div>
                <span className="font-medium text-muted-foreground">Generates: </span>
                {generates}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
