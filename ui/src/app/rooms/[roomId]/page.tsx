import { getSession } from '@/lib/auth'
import { redirect } from 'next/navigation'
import RoomClient from './RoomClient'

export default async function RoomPage({ params }: { params: Promise<{ roomId: string }> }) {
  const session = await getSession()
  if (!session) redirect('/login')
  const { roomId } = await params
  return <RoomClient roomId={roomId} user={session} />
}
