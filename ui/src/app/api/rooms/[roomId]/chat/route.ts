import { NextResponse } from 'next/server'
import { getChat, insertChat } from '@/lib/rooms-db'
import { agentFetch } from '@/lib/agent-fetch'

export async function GET(_: Request, { params }: { params: { roomId: string } }) {
  const messages = getChat(params.roomId)
  return NextResponse.json(messages)
}

export async function POST(req: Request, { params }: { params: { roomId: string } }) {
  try {
    const { content } = await req.json() as { content?: string }
    if (!content?.trim()) return NextResponse.json({ error: 'Empty message' }, { status: 400 })

    insertChat(params.roomId, 'user', content)

    const res = await agentFetch('/chat', {
      method: 'POST',
      body: JSON.stringify({
        message: content,
        session_id: `room-${params.roomId}`,
      }),
    })

    let reply = 'No response from agent'
    if (res.ok) {
      const data = await res.json() as { response?: string; message?: string }
      reply = data.response ?? data.message ?? JSON.stringify(data)
    }

    insertChat(params.roomId, 'assistant', reply)
    return NextResponse.json({ reply })
  } catch {
    return NextResponse.json({ error: 'Failed to process message' }, { status: 500 })
  }
}
