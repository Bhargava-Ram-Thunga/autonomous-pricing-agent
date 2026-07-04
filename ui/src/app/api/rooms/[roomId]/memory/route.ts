import { NextResponse } from 'next/server'
import { getMemory, setMemory } from '@/lib/rooms-db'

export async function GET(_: Request, { params }: { params: { roomId: string } }) {
  return NextResponse.json({ memory: getMemory(params.roomId) })
}

export async function PUT(req: Request, { params }: { params: { roomId: string } }) {
  const { memory } = await req.json() as { memory?: string }
  setMemory(params.roomId, memory ?? '')
  return NextResponse.json({ ok: true })
}
