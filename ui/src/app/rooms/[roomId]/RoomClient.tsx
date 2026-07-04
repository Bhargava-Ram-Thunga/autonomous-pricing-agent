'use client'
import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'

interface Message { id: number; role: string; content: string; created_at: string }
interface User { email: string; name: string }

export default function RoomClient({ roomId, user: _user }: { roomId: string; user: User }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [memory, setMemory] = useState('')
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [savingMemory, setSavingMemory] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch(`/api/rooms/${roomId}/chat`).then((r) => r.json()).then((d: Message[]) => setMessages(d))
    fetch(`/api/rooms/${roomId}/memory`).then((r) => r.json()).then((d: { memory: string }) => setMemory(d.memory ?? ''))
  }, [roomId])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  async function sendMessage() {
    if (!input.trim() || sending) return
    setSending(true)
    const content = input.trim()
    setInput('')
    setMessages((prev) => [...prev, { id: Date.now(), role: 'user', content, created_at: new Date().toISOString() }])
    try {
      const res = await fetch(`/api/rooms/${roomId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      })
      const data = await res.json() as { reply?: string }
      if (data.reply) {
        setMessages((prev) => [...prev, { id: Date.now() + 1, role: 'assistant', content: data.reply!, created_at: new Date().toISOString() }])
      }
    } catch {
      setMessages((prev) => [...prev, { id: Date.now() + 1, role: 'assistant', content: 'Error: could not reach agent', created_at: new Date().toISOString() }])
    } finally {
      setSending(false)
    }
  }

  async function saveMemory() {
    setSavingMemory(true)
    await fetch(`/api/rooms/${roomId}/memory`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ memory }),
    })
    setSavingMemory(false)
  }

  const parts = roomId.split('_')
  const svcNum = parts[0]
  const date = parts.slice(1).join('_')

  return (
    <div className="flex h-screen bg-gray-950">
      <div className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800">
          <Link href="/rooms" className="text-sm text-gray-400 hover:text-white">← Rooms</Link>
        </div>
        <nav className="p-3 space-y-1">
          <Link href="/rooms" className="text-gray-400 hover:bg-gray-800 px-3 py-2 rounded-lg text-sm block">Rooms</Link>
          <Link href="/feed" className="text-gray-400 hover:bg-gray-800 px-3 py-2 rounded-lg text-sm block">Agent Feed</Link>
          <Link href="/autoloop" className="text-gray-400 hover:bg-gray-800 px-3 py-2 rounded-lg text-sm block">Autoloop</Link>
        </nav>
      </div>
      <div className="flex-1 flex flex-col min-w-0">
        <div className="bg-gray-900 border-b border-gray-800 px-6 py-3">
          <div className="text-white font-semibold">Service {svcNum}</div>
          <div className="text-xs text-gray-400">Date: {date} · Room: {roomId}</div>
        </div>
        <div className="flex flex-1 min-h-0">
          <div className="flex-1 flex flex-col min-w-0">
            <div className="flex-1 overflow-auto p-4 space-y-3">
              {messages.length === 0 && <p className="text-gray-500 text-sm text-center mt-8">No messages yet. Start a conversation.</p>}
              {messages.map((m) => (
                <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[75%] rounded-xl px-4 py-2 text-sm ${m.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-100'}`}>
                    {m.content}
                  </div>
                </div>
              ))}
              {sending && (
                <div className="flex justify-start">
                  <div className="bg-gray-800 text-gray-400 rounded-xl px-4 py-2 text-sm animate-pulse">Agent thinking…</div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
            <div className="border-t border-gray-800 p-4 flex gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                placeholder="Type a message…"
                className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-600"
              />
              <button onClick={sendMessage} disabled={sending || !input.trim()} className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-xl text-sm font-medium">
                Send
              </button>
            </div>
          </div>
          <div className="w-64 border-l border-gray-800 flex flex-col bg-gray-900">
            <div className="px-4 py-3 border-b border-gray-800">
              <div className="text-sm font-medium text-white">Memory / Instructions</div>
              <div className="text-xs text-gray-400">Persists across sessions</div>
            </div>
            <textarea
              value={memory}
              onChange={(e) => setMemory(e.target.value)}
              placeholder="Add instructions or memory for this room…"
              className="flex-1 bg-transparent text-sm text-gray-200 p-4 resize-none focus:outline-none placeholder-gray-600"
            />
            <div className="p-3 border-t border-gray-800">
              <button onClick={saveMemory} disabled={savingMemory} className="w-full bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white text-sm py-2 rounded-lg font-medium">
                {savingMemory ? 'Saving…' : 'Save Memory'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
