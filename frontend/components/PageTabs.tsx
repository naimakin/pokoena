"use client";

import { useEffect, useState, type ReactNode } from "react";

/** Sub-pages of one menu entry, switched in place; the choice lives in the
 *  URL (?<param>=) so links and Back land on the same tab. */
export function PageTabs<K extends string>({
  tabs,
  initial,
  param,
  render,
}: {
  tabs: { key: K; label: string }[];
  initial: string | undefined;
  param: string;
  render: (key: K, strip: ReactNode) => ReactNode;
}) {
  const fromUrl = tabs.find((t) => t.key === initial)?.key ?? tabs[0].key;
  const [active, setActive] = useState<K>(fromUrl);
  // A link to the same page with another ?param= re-renders us with a new `initial`.
  useEffect(() => setActive(fromUrl), [fromUrl]);

  function pick(key: K) {
    setActive(key);
    const url = new URL(window.location.href);
    if (key === tabs[0].key) url.searchParams.delete(param);
    else url.searchParams.set(param, key);
    window.history.replaceState(null, "", url);
  }

  const strip = (
    <div className="page-tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={active === t.key}
          className={active === t.key ? "is-on" : undefined}
          onClick={() => pick(t.key)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
  return <>{render(active, strip)}</>;
}
