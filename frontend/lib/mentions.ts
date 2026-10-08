// @mentions in activity comments (backend: services/mentions.py). A comment
// stores a mention as `@[Full Name](user:<uuid>)`; the textarea shows people
// `@Full Name` and keeps the name → id map until the comment is posted.

export const MENTION_TOKEN = /@\[([^\]\n]{1,120})\]\(user:([0-9a-fA-F-]{36})\)/g;

export type MentionSegment = { kind: "text"; text: string } | { kind: "mention"; name: string; userId: string };

/** Split a stored body into plain text and mention chips. */
export function mentionSegments(body: string): MentionSegment[] {
  const out: MentionSegment[] = [];
  let last = 0;
  for (const m of body.matchAll(MENTION_TOKEN)) {
    const at = m.index ?? 0;
    if (at > last) out.push({ kind: "text", text: body.slice(last, at) });
    out.push({ kind: "mention", name: m[1], userId: m[2] });
    last = at + m[0].length;
  }
  if (last < body.length) out.push({ kind: "text", text: body.slice(last) });
  return out;
}

/** `@[Ana Demir](user:…)` → `@Ana Demir`. */
export function mentionPlainText(body: string): string {
  return body.replace(MENTION_TOKEN, (_all, name: string) => `@${name}`);
}

/** A stored body back in editable form: `@Name` text plus the name → id map
 *  for the people already tagged, so re-saving keeps their tokens. */
export function mentionEditable(body: string | null | undefined): { text: string; picked: Record<string, string> } {
  const picked: Record<string, string> = {};
  for (const m of (body ?? "").matchAll(MENTION_TOKEN)) picked[m[1]] = m[2];
  return { text: mentionPlainText(body ?? ""), picked };
}

/** Turn the `@Name` the person typed back into tokens, for the people they
 *  actually picked from the list (longest names first, so "Ana Demir" wins
 *  over "Ana"). Names they typed without picking stay plain text. */
export function serializeMentions(text: string, picked: Record<string, string>): string {
  let out = text;
  const names = Object.keys(picked).sort((a, b) => b.length - a.length);
  for (const name of names) {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    out = out.replace(new RegExp(`(^|[^\\w\\]])@${escaped}(?![\\w])`, "g"), (_all, lead: string) => `${lead}@[${name}](user:${picked[name]})`);
  }
  return out;
}
