import { useReducer, useEffect, useMemo, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useRepos, useStartSync } from '@/hooks/useSync'
import StepChooseScope from './steps/StepChooseScope'
import StepSelectRepos from './steps/StepSelectRepos'
import StepTimeRange from './steps/StepTimeRange'
import StepConfirm from './steps/StepConfirm'
import type { TimeRangeOption, SyncStartRequest } from '@/utils/types'

type WizardStep = 'scope' | 'repos' | 'time-range' | 'confirm'

interface WizardState {
  step: WizardStep
  syncType: 'full' | 'incremental'
  selectedRepoIds: number[]
  timeRange: TimeRangeOption
  customDate: string
}

type WizardAction =
  | { type: 'CUSTOM_SYNC' }
  | { type: 'SET_REPOS'; repoIds: number[] }
  | { type: 'SET_TIME_RANGE'; range: TimeRangeOption }
  | { type: 'SET_CUSTOM_DATE'; date: string }
  | { type: 'NEXT_STEP' }
  | { type: 'PREV_STEP' }
  | { type: 'RESET' }

const STEP_ORDER: WizardStep[] = ['scope', 'repos', 'time-range', 'confirm']
const STEP_LABELS = ['Scope', 'Repos', 'Time Range', 'Confirm']

const initialState: WizardState = {
  step: 'scope',
  syncType: 'incremental',
  selectedRepoIds: [],
  timeRange: 'since_last',
  customDate: '',
}

function reducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case 'CUSTOM_SYNC':
      return { ...state, step: 'repos', syncType: 'incremental' }
    case 'SET_REPOS':
      return { ...state, selectedRepoIds: action.repoIds }
    case 'SET_TIME_RANGE':
      return { ...state, timeRange: action.range }
    case 'SET_CUSTOM_DATE':
      return { ...state, customDate: action.date }
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
    default:
      return state
  }
}

function computeSinceDate(timeRange: TimeRangeOption, customDate: string): string | undefined {
  const now = new Date()
  const daysMap: Record<string, number> = {
    last_7d: 7, last_14d: 14, last_30d: 30, last_60d: 60, last_90d: 90,
  }
  if (daysMap[timeRange]) {
    const d = new Date(now.getTime() - daysMap[timeRange] * 86400000)
    return d.toISOString()
  }
  if (timeRange === 'custom' && customDate) {
    return new Date(customDate).toISOString()
  }
  // 'since_last' and 'all' have no override
  return undefined
}

export default function SyncWizard() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const { data: repos = [] } = useRepos()
  const startSync = useStartSync()

  // Pre-select tracked repos once on initial load
  const didAutoSelect = useRef(false)
  useEffect(() => {
    if (repos.length > 0 && !didAutoSelect.current) {
      didAutoSelect.current = true
      dispatch({
        type: 'SET_REPOS',
        repoIds: repos.filter((r) => r.is_tracked).map((r) => r.id),
      })
    }
  }, [repos])

  const selectedRepos = useMemo(
    () => repos.filter((r) => state.selectedRepoIds.includes(r.id)),
    [repos, state.selectedRepoIds],
  )

  const handleQuickSync = () => {
    startSync.mutate({ sync_type: 'incremental' })
  }

  const handleStartCustomSync = () => {
    const syncType = state.timeRange === 'since_last' ? 'incremental' : 'full'
    const request: SyncStartRequest = {
      sync_type: syncType,
      repo_ids: state.selectedRepoIds,
      since: computeSinceDate(state.timeRange, state.customDate),
    }
    startSync.mutate(request)
  }

  const currentStepIdx = STEP_ORDER.indexOf(state.step)

  return (
    <div className="space-y-4">
      {/* Step indicator — shown for custom sync flow */}
      {state.step !== 'scope' && (
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
              {i < STEP_ORDER.length - 1 && (
                <div className="mx-1 h-px w-6 bg-border" />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Step content */}
      {state.step === 'scope' && (
        <StepChooseScope
          onQuickSync={handleQuickSync}
          onCustomSync={() => dispatch({ type: 'CUSTOM_SYNC' })}
          disabled={startSync.isPending}
        />
      )}

      {state.step === 'repos' && (
        <div className="space-y-4">
          <StepSelectRepos
            repos={repos}
            selectedIds={state.selectedRepoIds}
            onChangeSelection={(ids) => dispatch({ type: 'SET_REPOS', repoIds: ids })}
          />
          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => dispatch({ type: 'PREV_STEP' })}>
              Back
            </Button>
            <Button
              onClick={() => dispatch({ type: 'NEXT_STEP' })}
              disabled={state.selectedRepoIds.length === 0}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      {state.step === 'time-range' && (
        <div className="space-y-4">
          <StepTimeRange
            timeRange={state.timeRange}
            customDate={state.customDate}
            repoCount={state.selectedRepoIds.length}
            onTimeRangeChange={(range) => dispatch({ type: 'SET_TIME_RANGE', range })}
            onCustomDateChange={(date) => dispatch({ type: 'SET_CUSTOM_DATE', date })}
          />
          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => dispatch({ type: 'PREV_STEP' })}>
              Back
            </Button>
            <Button
              onClick={() => dispatch({ type: 'NEXT_STEP' })}
              disabled={state.timeRange === 'custom' && !state.customDate}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      {state.step === 'confirm' && (
        <StepConfirm
          syncType={state.timeRange === 'since_last' ? 'incremental' : 'full'}
          selectedRepos={selectedRepos}
          timeRange={state.timeRange}
          customDate={state.customDate}
          onStart={handleStartCustomSync}
          onBack={() => dispatch({ type: 'PREV_STEP' })}
          isPending={startSync.isPending}
        />
      )}
    </div>
  )
}
