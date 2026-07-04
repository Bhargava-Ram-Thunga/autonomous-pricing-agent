"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Alert, Card, Chip, Skeleton } from "@heroui/react";
import { InboxIcon } from "lucide-react";

import { AppShell } from "@/components/app-shell";

interface Room {
  roomId: string;
  service: string;
  date: string;
  dep: string;
  booked: number;
  seats: number;
  occ: number;
  fare_adj: number;
  hasMemory: boolean;
}

interface User {
  email: string;
  name: string;
}

export default function RoomsClient({ user }: { user: User }) {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/rooms")
      .then((r) => r.json())
      .then(setRooms)
      .catch(() => setError("Failed to load rooms"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppShell user={user} title="Pricing Rooms">
      <div className="p-6">
        {error && (
          <Alert status="danger" className="mb-4">
            <Alert.Content>
              <Alert.Description>{error}</Alert.Description>
            </Alert.Content>
          </Alert>
        )}

        {loading && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-28 rounded-xl" />
            ))}
          </div>
        )}

        {!loading && !error && rooms.length === 0 && (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <InboxIcon className="text-muted size-10" />
            <div className="text-sm font-medium">No rooms found</div>
            <p className="text-muted max-w-xs text-xs">
              The backend may be offline, or no active trips exist yet.
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {rooms.map((room) => (
            <Link key={room.roomId} href={`/rooms/${room.roomId}`}>
              <Card className="hover:border-accent/50 h-full cursor-pointer transition-colors">
                <Card.Header className="flex-row items-start justify-between gap-2">
                  <Card.Title className="text-sm">{room.service}</Card.Title>
                  {room.hasMemory && (
                    <Chip size="sm" variant="soft">
                      <Chip.Label>Memory</Chip.Label>
                    </Chip>
                  )}
                </Card.Header>
                <Card.Content className="text-muted flex flex-col gap-1 text-xs">
                  <div>
                    Date: {room.date} · Dep: {room.dep}
                  </div>
                  <div>
                    Booked: {room.booked}/{room.seats} ({Math.round(room.occ * 100)}%)
                  </div>
                  {room.fare_adj !== 0 && (
                    <Chip
                      size="sm"
                      color={room.fare_adj > 0 ? "success" : "danger"}
                      className="mt-1 w-fit"
                    >
                      <Chip.Label>
                        {room.fare_adj > 0 ? "+" : ""}
                        {room.fare_adj}
                      </Chip.Label>
                    </Chip>
                  )}
                </Card.Content>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
