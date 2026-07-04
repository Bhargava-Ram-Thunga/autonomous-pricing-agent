import { getSession } from '@/lib/auth'
import { redirect } from 'next/navigation'
import RoomClient from './RoomClient'

export default async function RoomPage({ params }: { params: { roomId: string } }) {
  const session = await getSession()
  if (!session) redirect('/login')
  return <RoomClient roomId={params.roomId} user={session} />
}
