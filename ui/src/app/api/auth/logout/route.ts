import { NextResponse } from 'next/server'
import { getSessionCookieName } from '@/lib/auth'

export async function POST() {
  const res = NextResponse.json({ ok: true })
  res.cookies.delete(getSessionCookieName())
  return res
}
