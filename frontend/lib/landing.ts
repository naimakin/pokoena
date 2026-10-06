// The page a company user lands on after signing in ("Set as my landing
// page" in the user menu). Per browser, in localStorage — a convenience, so
// every read/write tolerates storage being unavailable and falls back to the
// role's default home.

const KEY = "poko:landing";

function isSafePath(path: string | null): path is string {
  return !!path && path.startsWith("/") && !path.startsWith("//") && !path.startsWith("/login");
}

export function getLandingPage(): string | null {
  try {
    const value = window.localStorage.getItem(KEY);
    return isSafePath(value) ? value : null;
  } catch {
    return null;
  }
}

export function setLandingPage(path: string | null): void {
  try {
    if (path && isSafePath(path)) window.localStorage.setItem(KEY, path);
    else window.localStorage.removeItem(KEY);
  } catch {
    // storage unavailable — the choice just won't stick
  }
}
