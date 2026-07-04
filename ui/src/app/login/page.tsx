'use client'
import { useState } from 'react'

export default function LoginPage() {
  const [loading, setLoading] = useState(false)
  const [demoLoading, setDemoLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleCredentialResponse(response: { credential: string }) {
    setLoading(true)
    try {
      const res = await fetch('/api/auth/google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idToken: response.credential }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError((data as { error?: string }).error ?? 'Authentication failed')
        return
      }
      window.location.href = '/rooms'
    } catch {
      setError('Network error during sign-in')
    } finally {
      setLoading(false)
    }
  }

  async function handleGoogleSignIn() {
    setLoading(true)
    setError(null)
    try {
      const g = (window as unknown as { google?: { accounts?: { id?: { prompt: () => void } } } }).google
      const client = g?.accounts?.id
      if (!client) {
        setError('Google sign-in not configured for this deployment.')
        setLoading(false)
        return
      }
      client.prompt()
    } catch {
      setError('Sign-in failed')
      setLoading(false)
    }
  }

  async function handleDemoSignIn() {
    setDemoLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/auth/demo', { method: 'POST' })
      if (!res.ok) {
        setError('Could not start demo session')
        return
      }
      window.location.href = '/rooms'
    } catch {
      setError('Network error starting demo session')
    } finally {
      setDemoLoading(false)
    }
  }

  return (
    <>
      <script
        src="https://accounts.google.com/gsi/client"
        onLoad={() => {
          const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID
          if (!clientId) return
          const g = (window as unknown as { google?: { accounts?: { id?: { initialize: (cfg: { client_id: string | undefined; callback: (r: { credential: string }) => void }) => void } } } }).google
          g?.accounts?.id?.initialize({
            client_id: clientId,
            callback: handleCredentialResponse,
          })
        }}
        async
        defer
      />
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background:
            'radial-gradient(circle at 20% 20%, rgba(79,142,247,0.14), transparent 45%), radial-gradient(circle at 80% 80%, rgba(52,211,153,0.10), transparent 45%), var(--color-bg)',
          padding: 20,
        }}
      >
        <div
          style={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: 20,
            padding: '40px 36px',
            width: '100%',
            maxWidth: 380,
            boxShadow: '0 20px 60px -20px rgba(0,0,0,0.6)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 20 }}>
            <div
              style={{
                width: 52,
                height: 52,
                borderRadius: 14,
                background: 'linear-gradient(135deg, var(--color-accent), var(--color-green))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 900,
                fontSize: 22,
                color: '#fff',
                boxShadow: '0 8px 24px -6px rgba(79,142,247,0.5)',
              }}
            >
              P
            </div>
          </div>
          <div style={{ marginBottom: 28, textAlign: 'center' }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--color-text)', marginBottom: 4 }}>
              Pricing Agent
            </div>
            <div style={{ fontSize: 13, color: 'var(--color-muted)' }}>
              Autonomous pricing, monitored live
            </div>
          </div>

          {error && (
            <div
              style={{
                marginBottom: 16,
                fontSize: 13,
                color: 'var(--color-red)',
                background: 'rgba(248,113,113,0.08)',
                border: '1px solid rgba(248,113,113,0.3)',
                borderRadius: 10,
                padding: '10px 12px',
              }}
            >
              {error}
            </div>
          )}

          <button
            onClick={handleGoogleSignIn}
            disabled={loading || demoLoading}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 10,
              background: '#fff',
              color: '#1a1d27',
              fontWeight: 500,
              fontSize: 14,
              padding: '11px 16px',
              borderRadius: 12,
              border: 'none',
              opacity: loading || demoLoading ? 0.6 : 1,
              transition: 'opacity 0.15s, transform 0.1s',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            {loading ? 'Signing in…' : 'Sign in with Google'}
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '20px 0' }}>
            <div style={{ flex: 1, height: 1, background: 'var(--color-border)' }} />
            <span style={{ fontSize: 11, color: 'var(--color-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>or</span>
            <div style={{ flex: 1, height: 1, background: 'var(--color-border)' }} />
          </div>

          <button
            onClick={handleDemoSignIn}
            disabled={loading || demoLoading}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              background: 'rgba(79,142,247,0.1)',
              color: 'var(--color-accent)',
              fontWeight: 500,
              fontSize: 14,
              padding: '11px 16px',
              borderRadius: 12,
              border: '1px solid rgba(79,142,247,0.3)',
              opacity: loading || demoLoading ? 0.6 : 1,
              transition: 'opacity 0.15s',
            }}
          >
            {demoLoading ? 'Starting demo…' : '→ Continue with Demo Access'}
          </button>

          <p style={{ marginTop: 20, fontSize: 11.5, color: 'var(--color-muted)', textAlign: 'center', lineHeight: 1.5 }}>
            Demo access skips Google auth for local evaluation.
            No real portal credentials are used.
          </p>
        </div>
      </div>
    </>
  )
}
