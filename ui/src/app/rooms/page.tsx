import { getSession } from '@/lib/auth'
import { redirect } from 'next/navigation'
import RoomsClient from './RoomsClient'

export default async function RoomsPage() {
  const session = await getSession()
  if (!session) redirect('/login')
  return <RoomsClient user={session} />
}
