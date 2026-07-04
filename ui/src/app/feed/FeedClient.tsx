'use client'
import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'

interface FeedEntry { id: number; text: string; ts: string }

export default function FeedClient() {
  const [entries, setEntries] = useState<FeedEntry[]>([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let es: EventSource | null = null
    let pollInterval: ReturnType<typeof setInterval> | null = null

    function startSSE() {
      try {
        es = new EventSource('/api/agent/chat/stream')
        es.onopen = () => { setConnected(true); setError(null) }
        es.onmessage = (e) => {
          try {
            const data: unknown = JSON.parse(e.data)
            setEntries((prev) => [...prev.slice(-199), { id: Date.now(), text: typeof data === 'string' ? data : JSON.stringify(data), ts: new Date().toLocaleTimeString() }])
          } catch {
            setEntries((prev) => [...prev.slice(-199), { id: Date.now(), text: e.data, ts: new Date().toLocaleTimeString() }])
          }
        }
        es.onerror = () => {
          setConnected(false)
          setError('SSE disconnected — falling back to polling')
          es?.close()
          startPolling()
        }
      } catch {
        startPolling()
      }
    }

    function startPolling() {
      pollInterval = setInterval(async () => {
        try {
          const res = await fetch('/api/agent/health')
          if (res.ok) setError('Backend alive (SSE unavailable — polling health)')
        } catch {
          setError('Backend unreachable')
        }
      }, 10000)
    }

    startSSE()
    return () => { es?.close(); if (pollInterval) clearInterval(pollInterval) }
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [entries])

  return (
    <div className="flex h-screen bg-gray-950">
      <div className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800 text-sm font-semibold text-white">Pricing Agent</div>
        <nav className="p-3 space-y-1">
          <Link href="/rooms" className="text-gray-400 hover:bg-gray-800 px-3 py-2 rounded-lg text-sm block">Rooms</Link>
          <Link href="/feed" className="bg-gray-800 text-white px-3 py-2 rounded-lg text-sm block">Agent Feed</Link>
          <Link href="/autoloop" className="text-gray-400 hover:bg-gray-800 px-3 py-2 rounded-lg text-sm block">Autoloop</Link>
        </nav>
      </div>
      <div className="flex-1 flex flex-col">
        <div className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center gap-3">
          <div className="text-white font-semibold">Agent Live Feed</div>
          <span className={`text-xs px-2 py-0.5 rounded-full ${connected ? 'bg-green-900 text-green-300' : 'bg-gray-800 text-gray-400'}`}>
            {connected ? 'Live' : 'Offline'}
          </span>
        </div>
        {error && <div className="text-xs text-yellow-400 bg-yellow-950 px-4 py-2">{error}</div>}
        <div className="flex-1 overflow-auto p-4 font-mono text-sm space-y-1">
          {entries.length === 0 && (
            <p className="text-gray-500 text-center mt-12">Waiting for agent activity…</p>
          )}
          {entries.map((e) => (
            <div key={e.id} className="flex gap-2">
              <span className="text-gray-600 shrink-0">{e.ts}</span>
              <span className="text-gray-300">{e.text}</span>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  )
}
