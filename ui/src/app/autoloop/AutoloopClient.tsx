'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'

interface AutoloopStatus { running: boolean; paused?: boolean; last_run?: string; next_run?: string }

export default function AutoloopClient() {
  const [status, setStatus] = useState<AutoloopStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [acting, setActing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function fetchStatus() {
    try {
      const res = await fetch('/api/agent/autoloop/status')
      if (res.ok) setStatus(await res.json() as AutoloopStatus)
      else setError('Could not fetch status')
    } catch {
      setError('Backend unreachable')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchStatus(); const t = setInterval(fetchStatus, 15000); return () => clearInterval(t) }, [])

  async function action(endpoint: string) {
    setActing(true)
    try {
      const res = await fetch(`/api/agent/${endpoint}`, { method: 'POST' })
      if (!res.ok) throw new Error('Action failed')
      await fetchStatus()
    } catch {
      setError('Action failed')
    } finally {
      setActing(false)
    }
  }

  const isPaused = !status?.running || (status?.paused === true)

  return (
    <div className="flex h-screen bg-gray-950">
      <div className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800 text-sm font-semibold text-white">Pricing Agent</div>
        <nav className="p-3 space-y-1">
          <Link href="/rooms" className="text-gray-400 hover:bg-gray-800 px-3 py-2 rounded-lg text-sm block">Rooms</Link>
          <Link href="/feed" className="text-gray-400 hover:bg-gray-800 px-3 py-2 rounded-lg text-sm block">Agent Feed</Link>
          <Link href="/autoloop" className="bg-gray-800 text-white px-3 py-2 rounded-lg text-sm block">Autoloop</Link>
        </nav>
      </div>
      <div className="flex-1 p-8">
        <h1 className="text-xl font-bold text-white mb-6">Autoloop Control</h1>
        {loading && <p className="text-gray-400">Loading status…</p>}
        {error && <p className="text-red-400 mb-4">{error}</p>}
        {status && (
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 max-w-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className={`w-3 h-3 rounded-full ${isPaused ? 'bg-yellow-400' : 'bg-green-400'}`} />
              <div className="text-white font-medium">{isPaused ? 'Paused' : 'Running'}</div>
            </div>
            {status.last_run && <div className="text-xs text-gray-400 mb-1">Last run: {status.last_run}</div>}
            {status.next_run && <div className="text-xs text-gray-400 mb-4">Next run: {status.next_run}</div>}
            <div className="flex gap-3">
              <button
                onClick={() => action('autoloop/pause')}
                disabled={acting || isPaused}
                className="flex-1 bg-yellow-600 hover:bg-yellow-700 disabled:opacity-40 text-white py-2 rounded-xl text-sm font-medium"
              >
                Pause
              </button>
              <button
                onClick={() => action('autoloop/resume')}
                disabled={acting || !isPaused}
                className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-40 text-white py-2 rounded-xl text-sm font-medium"
              >
                Resume
              </button>
            </div>
          </div>
        )}
        {!loading && !status && !error && (
          <div className="text-gray-500">Backend offline. Start the FastAPI backend first.</div>
        )}
      </div>
    </div>
  )
}
