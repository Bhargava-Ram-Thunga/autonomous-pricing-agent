import { NextResponse } from 'next/server'
import { createSessionToken, getSessionCookieName } from '@/lib/auth'
import { agentFetch } from '@/lib/agent-fetch'

export async function POST(req: Request) {
  try {
    const { idToken } = await req.json() as { idToken?: string }
    if (!idToken) return NextResponse.json({ error: 'Missing idToken' }, { status: 400 })

    const parts = idToken.split('.')
    if (parts.length < 2) return NextResponse.json({ error: 'Invalid token' }, { status: 400 })
    const payload = JSON.parse(
      Buffer.from(parts[1], 'base64url').toString()
    ) as { email?: string; name?: string; picture?: string }
    const email: string = payload.email ?? ''
    const name: string = payload.name ?? email
    const picture: string = payload.picture ?? ''

    if (!email) return NextResponse.json({ error: 'No email in token' }, { status: 400 })

    try {
      await agentFetch('/auth/google', {
        method: 'POST',
        body: JSON.stringify({ id_token: idToken }),
      })
    } catch {
      // Backend auth is optional
    }

    const token = await createSessionToken({ email, name, picture })
    const res = NextResponse.json({ ok: true, email, name })
    res.cookies.set(getSessionCookieName(), token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 60 * 60 * 24 * 7,
      path: '/',
    })
    return res
  } catch {
    return NextResponse.json({ error: 'Authentication failed' }, { status: 500 })
  }
}
