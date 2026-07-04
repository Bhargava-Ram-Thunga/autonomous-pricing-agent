import { cookies } from 'next/headers'
import { jwtVerify, SignJWT } from 'jose'

const SECRET = new TextEncoder().encode(
  process.env.NEXTAUTH_SECRET ?? 'dev-secret-change-in-production'
)
const COOKIE = 'pb_session'

export interface SessionUser {
  email: string
  name: string
  picture?: string
}

export async function getSession(): Promise<SessionUser | null> {
  const store = await cookies()
  const token = store.get(COOKIE)?.value
  if (!token) return null
  try {
    const { payload } = await jwtVerify(token, SECRET)
    return payload as unknown as SessionUser
  } catch {
    return null
  }
}

export async function createSessionToken(user: SessionUser): Promise<string> {
  return new SignJWT({ ...user })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime('7d')
    .sign(SECRET)
}

export function getSessionCookieName() {
  return COOKIE
}
