import { NextResponse } from 'next/server'
import { getMemory, setMemory } from '@/lib/rooms-db'

export async function GET(_: Request, { params }: { params: Promise<{ roomId: string }> }) {
  const { roomId } = await params
  return NextResponse.json({ memory: getMemory(roomId) })
}

export async function PUT(req: Request, { params }: { params: Promise<{ roomId: string }> }) {
  const { roomId } = await params
  const { memory } = await req.json() as { memory?: string }
  setMemory(roomId, memory ?? '')
  return NextResponse.json({ ok: true })
}
