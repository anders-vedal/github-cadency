import { useReducer, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useRunAnalysis, useRunOneOnOnePrep, useRunTeamHealth } from '@/hooks/useAI'
import { useCreateAISchedule } from '@/hooks/useAISchedules'
import { useDevelopers } from '@/hooks/useDevelopers'
import StepChooseType from './steps/StepChooseType'
import StepConfigureScope from './steps/StepConfigureScope'
import StepTimeRange from './steps/StepTimeRange'
import StepConfirm from './steps/StepConfirm'
import type { AnalysisWizardType, TimeRangeOption } from '@/utils/types'

type WizardStep = 'type' | 'scope' | 'time-range' | 'confirm'

interface WizardState {
  step: WizardStep
  analysisType: AnalysisWizardType | null
  scopeType: 'developer' | 'team' | 'repo' | null
  scopeId: string
  scopeName: string
  timeRange: TimeRangeOption
  customDate: string
  repoIds: number[]
}

type WizardAction =
  | { type: 'SET_ANALYSIS_TYPE'; analysisType: AnalysisWizardType }
  | { type: 'SET_SCOPE_TYPE'; scopeType: 'developer' | 'team' | 'repo' }
  | { type: 'SET_SCOPE'; scopeId: string; scopeName: string }
  | { type: 'SET_TIME_RANGE'; range: TimeRangeOption }
  | { type: 'SET_CUSTOM_DATE'; date: string }
  | { type: 'SET_REPO_IDS'; repoIds: number[] }
  | { type: 'NEXT_STEP' }
  | { type: 'PREV_STEP' }
  | { type: 'RESET' }
  | { type: 'PREFILL'; state: Partial<WizardState> }

const STEP_ORDER: WizardStep[] = ['type', 'scope', 'time-range', 'confirm']
const STEP_LABELS = ['Analysis Type', 'Scope', 'Time Range', 'Confirm']

const initialState: WizardState = {
  step: 'type',
  analysisType: null,
  scopeType: null,
  scopeId: '',
  scopeName: '',
  timeRange: 'last_30d',
  customDate: '',
  repoIds: [],
}

function getDefaultScopeType(analysisType: AnalysisWizardType): 'developer' | 'team' | 'repo' | null {
  switch (analysisType) {
    case 'communication':
    case 'one_on_one_prep':
      return 'developer'
    case 'conflict':
    case 'team_health':
      return 'team'
    case 'sentiment':
      return null // user chooses
  }
}

function reducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case 'SET_ANALYSIS_TYPE': {
      const scopeType = getDefaultScopeType(action.analysisType)
      return {
        ...state,
        analysisType: action.analysisType,
        scopeType,
        scopeId: '',
        scopeName: '',
      }
    }
    case 'SET_SCOPE_TYPE':
      return { ...state, scopeType: action.scopeType, scopeId: '', scopeName: '' }
    case 'SET_SCOPE':
      return { ...state, scopeId: action.scopeId, scopeName: action.scopeName }
    case 'SET_TIME_RANGE':
      return { ...state, timeRange: action.range }
    case 'SET_CUSTOM_DATE':
      return { ...state, customDate: action.date }
    case 'SET_REPO_IDS':
      return { ...state, repoIds: action.repoIds }
    case 'NEXT_STEP': {
      const idx = STEP_ORDER.indexOf(state.step)
      if (idx < STEP_ORDER.length - 1) return { ...state, step: STEP_ORDER[idx + 1] }
      return state
    }
    case 'PREV_STEP': {
      const idx = STEP_ORDER.indexOf(state.step)
      if (idx > 0) return { ...state, step: STEP_ORDER[idx - 1] }
      return state
    }
    case 'RESET':
      return initialState
    case 'PREFILL':
      return { ...state, ...action.state }
    default:
      return state
  }
}

function computeSinceDate(timeRange: TimeRangeOption, customDate: string): string {
  const now = new Date()
  const daysMap: Record<string, number> = {
    last_7d: 7, last_14d: 14, last_30d: 30, last_60d: 60, last_90d: 90,
  }
  if (daysMap[timeRange]) {
    return new Date(now.getTime() - daysMap[timeRange] * 86400000).toISOString()
  }
  if (timeRange === 'custom' && customDate) {
    return new Date(customDate).toISOString()
  }
  return new Date(now.getTime() - 30 * 86400000).toISOString()
}

const timeRangeToDays: Partial<Record<TimeRangeOption, number>> = {
  last_7d: 7, last_14d: 14, last_30d: 30, last_60d: 60, last_90d: 90,
}

export default function AIWizard() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { data: developers = [] } = useDevelopers()

  const runAnalysis = useRunAnalysis()
  const runOneOnOnePrep = useRunOneOnOnePrep()
  const runTeamHealth = useRunTeamHealth()
  const createSchedule = useCreateAISchedule()

  // Pre-fill from URL params on mount
  const didPrefill = useRef(false)
  useEffect(() => {
    if (didPrefill.current) return

    const typeParam = searchParams.get('type') as AnalysisWizardType | null
    const devId = searchParams.get('developer_id')

    // If developer_id is specified, wait until developers data loads
    if (devId && developers.length === 0) return

    didPrefill.current = true

    if (typeParam) {
      const prefill: Partial<WizardState> = {
        analysisType: typeParam,
        scopeType: getDefaultScopeType(typeParam),
        step: 'scope',
      }

      if (devId) {
        const dev = developers.find((d) => String(d.id) === devId)
        if (dev) {
          prefill.scopeId = devId
          prefill.scopeName = `${dev.display_name} (@${dev.github_username})`
        }
      }

      dispatch({ type: 'PREFILL', state: prefill })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [developers])

  const currentStepIdx = STEP_ORDER.indexOf(state.step)

  const dateFrom = computeSinceDate(state.timeRange, state.customDate)
  const dateTo = new Date().toISOString()

  const handleRun = () => {
    const repoIds = state.repoIds.length > 0 ? state.repoIds : undefined

    if (state.analysisType === 'one_on_one_prep') {
      runOneOnOnePrep.mutate(
        {
          data: {
            developer_id: Number(state.scopeId),
            date_from: dateFrom,
            date_to: dateTo,
            repo_ids: repoIds,
          },
        },
        { onSuccess: () => navigate('/admin/ai') },
      )
    } else if (state.analysisType === 'team_health') {
      runTeamHealth.mutate(
        {
          data: {
            ...(state.scopeId && state.scopeId !== '__all__' ? { team: state.scopeId } : {}),
            date_from: dateFrom,
            date_to: dateTo,
            repo_ids: repoIds,
          },
        },
        { onSuccess: () => navigate('/admin/ai') },
      )
    } else if (state.analysisType) {
      runAnalysis.mutate(
        {
          data: {
            analysis_type: state.analysisType as 'communication' | 'conflict' | 'sentiment',
            scope_type: state.scopeType as 'developer' | 'team' | 'repo',
            scope_id: state.scopeId,
            date_from: dateFrom,
            date_to: dateTo,
            repo_ids: repoIds,
          },
        },
        { onSuccess: () => navigate('/admin/ai') },
      )
    }
  }

  const handleSchedule = (schedule: {
    name: string
    frequency: string
    day_of_week?: number
    hour: number
    minute: number
  }) => {
    const isGeneral = ['communication', 'conflict', 'sentiment'].includes(state.analysisType ?? '')
    createSchedule.mutate(
      {
        name: schedule.name,
        analysis_type: isGeneral ? 'general_analysis' : (state.analysisType ?? ''),
        general_type: isGeneral ? state.analysisType ?? undefined : undefined,
        scope_type: state.scopeType ?? 'developer',
        scope_id: state.scopeId === '__all__' ? 'all' : state.scopeId,
        repo_ids: state.repoIds.length > 0 ? state.repoIds : undefined,
        time_range_days: timeRangeToDays[state.timeRange] ?? 30,
        frequency: schedule.frequency,
        day_of_week: schedule.day_of_week,
        hour: schedule.hour,
        minute: schedule.minute,
      },
      { onSuccess: () => navigate('/admin/ai') },
    )
  }

  const isRunning = runAnalysis.isPending || runOneOnOnePrep.isPending || runTeamHealth.isPending
  const isScheduling = createSchedule.isPending

  const canAdvance = (): boolean => {
    switch (state.step) {
      case 'type':
        return state.analysisType !== null
      case 'scope':
        return state.scopeId !== ''
      case 'time-range':
        return state.timeRange !== 'custom' || !!state.customDate
      default:
        return false
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">New AI Analysis</h1>
        <Button variant="ghost" onClick={() => navigate('/admin/ai')}>
          Cancel
        </Button>
      </div>

      {/* Step indicator */}
      {state.step !== 'type' && (
        <div className="flex items-center gap-2">
          {STEP_ORDER.map((step, i) => (
            <div key={step} className="flex items-center gap-2">
              <div
                className={cn(
                  'flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium',
                  i < currentStepIdx
                    ? 'bg-primary text-primary-foreground'
                    : i === currentStepIdx
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground',
                )}
              >
                {i < currentStepIdx ? '\u2713' : i + 1}
              </div>
              <span
                className={cn(
                  'text-xs',
                  i === currentStepIdx ? 'font-medium' : 'text-muted-foreground',
                )}
              >
                {STEP_LABELS[i]}
              </span>
              {i < STEP_ORDER.length - 1 && <div className="mx-1 h-px w-6 bg-border" />}
            </div>
          ))}
        </div>
      )}

      {/* Step content */}
      {state.step === 'type' && (
        <div className="space-y-4">
          <StepChooseType
            selected={state.analysisType}
            onSelect={(type) => dispatch({ type: 'SET_ANALYSIS_TYPE', analysisType: type })}
          />
          <div className="flex justify-end">
            <Button onClick={() => dispatch({ type: 'NEXT_STEP' })} disabled={!canAdvance()}>
              Next
            </Button>
          </div>
        </div>
      )}

      {state.step === 'scope' && state.analysisType && (
        <div className="space-y-4">
          <StepConfigureScope
            analysisType={state.analysisType}
            scopeType={state.scopeType}
            scopeId={state.scopeId}
            onScopeTypeChange={(st) => dispatch({ type: 'SET_SCOPE_TYPE', scopeType: st })}
            onScopeSelect={(id, name) => dispatch({ type: 'SET_SCOPE', scopeId: id, scopeName: name })}
          />
          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => dispatch({ type: 'PREV_STEP' })}>Back</Button>
            <Button onClick={() => dispatch({ type: 'NEXT_STEP' })} disabled={!canAdvance()}>Next</Button>
          </div>
        </div>
      )}

      {state.step === 'time-range' && (
        <div className="space-y-4">
          <StepTimeRange
            timeRange={state.timeRange}
            customDate={state.customDate}
            repoIds={state.repoIds}
            onTimeRangeChange={(range) => dispatch({ type: 'SET_TIME_RANGE', range })}
            onCustomDateChange={(date) => dispatch({ type: 'SET_CUSTOM_DATE', date })}
            onRepoIdsChange={(ids) => dispatch({ type: 'SET_REPO_IDS', repoIds: ids })}
          />
          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => dispatch({ type: 'PREV_STEP' })}>Back</Button>
            <Button onClick={() => dispatch({ type: 'NEXT_STEP' })} disabled={!canAdvance()}>Next</Button>
          </div>
        </div>
      )}

      {state.step === 'confirm' && state.analysisType && state.scopeType && (
        <StepConfirm
          analysisType={state.analysisType}
          scopeType={state.scopeType}
          scopeId={state.scopeId}
          scopeName={state.scopeName}
          timeRange={state.timeRange}
          customDate={state.customDate}
          repoIds={state.repoIds}
          dateFrom={dateFrom}
          dateTo={dateTo}
          onRun={handleRun}
          onSchedule={handleSchedule}
          onBack={() => dispatch({ type: 'PREV_STEP' })}
          isRunning={isRunning}
          isScheduling={isScheduling}
        />
      )}
    </div>
  )
}
