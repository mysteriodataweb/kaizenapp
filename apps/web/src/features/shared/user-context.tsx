"use client";

import { createContext, type ReactNode, useContext } from "react";

import type { User } from "@/lib/types";

const UserContext = createContext<User | null>(null);

export function UserProvider({ user, children }: { user: User; children: ReactNode }) {
  return <UserContext.Provider value={user}>{children}</UserContext.Provider>;
}

export function useUser(): User {
  const user = useContext(UserContext);
  if (!user) throw new Error("useUser hors du layout privé");
  return user;
}
