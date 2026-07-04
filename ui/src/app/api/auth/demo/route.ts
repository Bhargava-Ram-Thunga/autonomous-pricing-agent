import { NextResponse } from 'next/server'
import { createSessionToken, getSessionCookieName } from '@/lib/auth'

export async function POST() {
  const token = await createSessionToken({
    email: 'demo@pricing-agent.local',
    name: 'Demo User',
  })
  const res = NextResponse.json({ ok: true })
  res.cookies.set(getSessionCookieName(), token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 24,
    path: '/',
  })
  return res
}
