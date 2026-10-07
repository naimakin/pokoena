import { mentionSegments } from "@/lib/mentions";

/** A comment body with its @mentions drawn as chips. */
export function MentionText({ body }: { body: string }) {
  return (
    <>
      {mentionSegments(body).map((seg, i) =>
        seg.kind === "text" ? (
          <span key={i}>{seg.text}</span>
        ) : (
          <span key={i} className="mention-chip">
            @{seg.name}
          </span>
        ),
      )}
    </>
  );
}
