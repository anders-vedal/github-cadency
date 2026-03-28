import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

export default function AuthCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  useEffect(() => {
    const token = searchParams.get('token')
    const code = searchParams.get('code')
    if (token) {
      localStorage.setItem('devpulse_token', token)
      navigate('/', { replace: true })
    } else if (code) {
      // GitHub redirected here with an OAuth code — forward to backend for token exchange
      window.location.href = `/api/auth/callback?code=${encodeURIComponent(code)}`
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
