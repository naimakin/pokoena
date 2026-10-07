"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { User } from "@/lib/types";

const CurrentUserContext = createContext<User | null>(null);

/** The signed-in user as the company shell loaded it (/auth/me), so pages can
 *  show or hide controls by capability without fetching it again. */
export function CurrentUserProvider({ user, children }: { user: User | null; children: ReactNode }) {
  return <CurrentUserContext.Provider value={user}>{children}</CurrentUserContext.Provider>;
}

export function useCurrentUser(): User | null {
  return useContext(CurrentUserContext);
}
