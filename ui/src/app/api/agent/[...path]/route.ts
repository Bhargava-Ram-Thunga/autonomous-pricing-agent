import { NextResponse } from 'next/server'
import { agentFetch } from '@/lib/agent-fetch'

async function proxy(req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params
  const p = '/' + path.join('/')
  const url = new URL(req.url)
  const fullPath = p + (url.search || '')
  try {
    const body = req.method !== 'GET' && req.method !== 'HEAD' ? await req.text() : undefined
    const res = await agentFetch(fullPath, {
      method: req.method,
      body,
    })
    const text = await res.text()
    return new Response(text, {
      status: res.status,
      headers: { 'Content-Type': res.headers.get('Content-Type') || 'application/json' },
    })
  } catch {
    return NextResponse.json({ error: 'Backend unavailable' }, { status: 502 })
  }
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE }
