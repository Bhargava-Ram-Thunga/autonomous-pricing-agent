import { NextResponse } from 'next/server'
import { getAllMemory } from '@/lib/rooms-db'
import { agentFetch } from '@/lib/agent-fetch'

export async function GET() {
  try {
    const res = await agentFetch('/trips')
    if (!res.ok) throw new Error('Backend unavailable')
    const trips = await res.json() as Array<{ svc: string; date: string; dep: string; booked: number; seats: number; occ: number; fare_adj: number }>
    const memories = getAllMemory()
    const memMap = Object.fromEntries(memories.map((m) => [m.room_id, m]))
    const rooms = trips.map((t) => ({
      roomId: `${t.svc}_${t.date}`,
      service: t.svc,
      date: t.date,
      dep: t.dep,
      booked: t.booked,
      seats: t.seats,
      occ: t.occ,
      fare_adj: t.fare_adj,
      hasMemory: !!memMap[`${t.svc}_${t.date}`],
    }))
    return NextResponse.json(rooms)
  } catch {
    return NextResponse.json([], { status: 200 })
  }
}
