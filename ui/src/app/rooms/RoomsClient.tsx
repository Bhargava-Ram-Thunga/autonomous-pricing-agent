'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'

interface Room {
  roomId: string
  service: string
  date: string
  dep: string
  booked: number
  seats: number
  occ: number
  fare_adj: number
  hasMemory: boolean
}

interface User { email: string; name: string }

export default function RoomsClient({ user }: { user: User }) {
  const [rooms, setRooms] = useState<Room[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/rooms')
      .then((r) => r.json())
      .then(setRooms)
      .catch(() => setError('Failed to load rooms'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="flex h-screen bg-gray-950">
      <div className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800">
          <div className="text-sm font-semibold text-white">Pricing Agent</div>
          <div className="text-xs text-gray-400 truncate">{user.email}</div>
        </div>
        <nav className="p-3 space-y-1">
          <Link href="/rooms" className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 text-white text-sm">Rooms</Link>
          <Link href="/feed" className="flex items-center gap-2 px-3 py-2 rounded-lg text-gray-400 hover:bg-gray-800 hover:text-white text-sm">Agent Feed</Link>
          <Link href="/autoloop" className="flex items-center gap-2 px-3 py-2 rounded-lg text-gray-400 hover:bg-gray-800 hover:text-white text-sm">Autoloop</Link>
        </nav>
      </div>
      <div className="flex-1 overflow-auto p-6">
        <h1 className="text-xl font-bold text-white mb-4">Pricing Rooms</h1>
        {loading && <p className="text-gray-400">Loading rooms…</p>}
        {error && <p className="text-red-400">{error}</p>}
        {!loading && !error && rooms.length === 0 && (
          <p className="text-gray-500">No rooms found. Backend may be offline.</p>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {rooms.map((room) => (
            <Link key={room.roomId} href={`/rooms/${room.roomId}`}>
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-blue-600 transition-colors cursor-pointer">
                <div className="flex justify-between items-start mb-2">
                  <div className="font-semibold text-white text-sm">{room.service}</div>
                  {room.hasMemory && <span className="text-xs bg-blue-900 text-blue-300 px-2 py-0.5 rounded-full">Memory</span>}
                </div>
                <div className="text-xs text-gray-400 space-y-1">
                  <div>Date: {room.date} · Dep: {room.dep}</div>
                  <div>Booked: {room.booked}/{room.seats} ({Math.round(room.occ * 100)}%)</div>
                  {room.fare_adj !== 0 && <div className={room.fare_adj > 0 ? 'text-green-400' : 'text-red-400'}>Adj: {room.fare_adj > 0 ? '+' : ''}{room.fare_adj}</div>}
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
