import { getSession } from '@/lib/auth'
import { redirect } from 'next/navigation'
import AutoloopClient from './AutoloopClient'

export default async function AutoloopPage() {
  const session = await getSession()
  if (!session) redirect('/login')
  return <AutoloopClient />
}
