const AGENT_URL = process.env.PRICING_AGENT_API_BASE_URL || process.env.NEXT_PUBLIC_AGENT_API_BASE_URL || 'http://localhost:8000'
const AGENT_KEY = (process.env.PRICING_AGENT_API_KEY ?? '').replace(/^"+|"+$/g, '')

export async function agentFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${AGENT_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': AGENT_KEY,
      ...(init?.headers ?? {}),
    },
  })
}
