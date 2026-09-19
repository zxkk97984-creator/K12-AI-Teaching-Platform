/**
 * Practice cache (T17 J5/J10).
 *
 * Only the *quiz session id* is cached — never answers, never verdicts (those
 * always come from a fresh server read) — and it is namespaced per user id.
 * When a different account logs in on the same browser, every other user's
 * namespace is purged before any read, so student B can never resume A's quiz
 * from the local cache. Ownership is still enforced by the backend: a cached
 * id from another account answers 404.
 */

const PREFIX = "k12.quiz.cache.v1";
const ACTIVE_USER = `${PREFIX}.activeUser`;

type Entry = { quizSessionId: string; lessonSessionId: string | null; updatedAt: string };
type Store = Record<string, Entry>;

function userKey(userId: string): string {
  return `${PREFIX}.${userId}`;
}

function safeStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/**
 * Drop every other account's namespace before reading the current one. This is
 * deliberately independent of the previous marker: even a browser that never
 * saw the previous login must not keep a stale student's quiz id around.
 */
export function adoptUser(userId: string): void {
  const storage = safeStorage();
  if (!storage) return;
  const mine = userKey(userId);
  const doomed: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key && key.startsWith(PREFIX) && key !== ACTIVE_USER && key !== mine) doomed.push(key);
  }
  doomed.forEach((key) => storage.removeItem(key));
  storage.setItem(ACTIVE_USER, userId);
}

export function readEntry(userId: string, chapterId: string): Entry | null {
  const storage = safeStorage();
  if (!storage) return null;
  const raw = storage.getItem(userKey(userId));
  if (!raw) return null;
  try {
    const store = JSON.parse(raw) as Store;
    const entry = store[chapterId];
    return entry && typeof entry.quizSessionId === "string" ? entry : null;
  } catch {
    storage.removeItem(userKey(userId));
    return null;
  }
}

export function writeEntry(userId: string, chapterId: string, entry: Omit<Entry, "updatedAt">): void {
  const storage = safeStorage();
  if (!storage) return;
  let store: Store = {};
  const raw = storage.getItem(userKey(userId));
  if (raw) {
    try {
      store = JSON.parse(raw) as Store;
    } catch {
      store = {};
    }
  }
  store[chapterId] = { ...entry, updatedAt: new Date().toISOString() };
  storage.setItem(userKey(userId), JSON.stringify(store));
}

export function clearEntry(userId: string, chapterId: string): void {
  const storage = safeStorage();
  if (!storage) return;
  const raw = storage.getItem(userKey(userId));
  if (!raw) return;
  try {
    const store = JSON.parse(raw) as Store;
    delete store[chapterId];
    storage.setItem(userKey(userId), JSON.stringify(store));
  } catch {
    storage.removeItem(userKey(userId));
  }
}
