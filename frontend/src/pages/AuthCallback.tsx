import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

export default function AuthCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  useEffect(() => {
    // Check URL fragment first (secure token delivery)
    const hash = window.location.hash
    if (hash) {
      const fragmentParams = new URLSearchParams(hash.substring(1))
      const token = fragmentParams.get('token')
      if (token) {
        localStorage.setItem('devpulse_token', token)
        // Full page reload instead of SPA navigate: useAuthProvider captures
        // the token from localStorage at hook-invocation time and won't re-read
        // it on React re-render. A reload gives the app a fresh JS context so
        // the /auth/me query fires with the new token.
        window.location.href = '/'
        return
      }
    }

    // GitHub redirected here with an OAuth code — forward to backend for token exchange
    const code = searchParams.get('code')
    const state = searchParams.get('state')
    if (code) {
      const params = new URLSearchParams({ code })
      if (state) params.set('state', state)
      window.location.href = `/api/auth/callback?${params.toString()}`
    } else {
      navigate('/login', { replace: true })
    }
  }, [searchParams, navigate])

  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-muted-foreground">
      Signing in...
    </div>
  )
}
