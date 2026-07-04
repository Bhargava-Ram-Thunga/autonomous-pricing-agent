"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Avatar, Surface } from "@heroui/react";
import { GaugeIcon, RadioIcon, TrendingUpIcon, WorkflowIcon } from "lucide-react";

const NAV = [
  { href: "/rooms", label: "Rooms", icon: GaugeIcon },
  { href: "/feed", label: "Agent Feed", icon: RadioIcon },
  { href: "/autoloop", label: "Autoloop", icon: WorkflowIcon },
];

function AppSidebar({ user }: { user?: { email: string; name?: string } }) {
  const pathname = usePathname();

  return (
    <Surface className="bg-surface border-border flex w-56 shrink-0 flex-col border-r">
      <div className="border-border flex items-center gap-2 border-b px-4 py-4">
        <div className="bg-accent text-accent-foreground flex size-7 shrink-0 items-center justify-center rounded-lg">
          <TrendingUpIcon className="size-4" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">Pricing Agent</div>
          {user?.email && <div className="text-muted truncate text-xs">{user.email}</div>}
        </div>
      </div>
      <nav className="flex flex-col gap-1 p-3">
        {NAV.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={
                active
                  ? "bg-accent-soft text-accent-soft-foreground flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium"
                  : "text-muted hover:bg-surface-secondary hover:text-foreground flex items-center gap-2 rounded-lg px-3 py-2 text-sm"
              }
            >
              <item.icon className="size-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      {user && (
        <div className="border-border mt-auto flex items-center gap-2 border-t p-3">
          <Avatar size="sm">
            <Avatar.Fallback>{(user.name ?? user.email).slice(0, 1).toUpperCase()}</Avatar.Fallback>
          </Avatar>
          <span className="text-muted truncate text-xs">{user.name ?? user.email}</span>
        </div>
      )}
    </Surface>
  );
}

export function AppShell({
  user,
  title,
  headerRight,
  children,
}: {
  user?: { email: string; name?: string };
  title: string;
  headerRight?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex h-screen">
      <AppSidebar user={user} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-border bg-surface flex h-14 shrink-0 items-center gap-2 border-b px-5">
          <h1 className="text-sm font-semibold">{title}</h1>
          <div className="ml-auto flex items-center gap-2">{headerRight}</div>
        </header>
        <div className="flex-1 overflow-auto">{children}</div>
      </div>
    </div>
  );
}
