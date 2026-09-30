import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;

/* Brand glyph — start node → stepped FS logic → finish milestone.
   24-unit grid, currentColor. Not an .icon: carries its own stroke attrs. */
export function PokoGlyph({ width = 16, height = 16, ...rest }: P) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={width}
      height={height}
      fill="none"
      stroke="currentColor"
      strokeWidth={2.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      <path d="M5.5 6H11.5V11.5H17V14" />
      <circle cx="5.5" cy="6" r="2.25" fill="currentColor" stroke="none" />
      <path d="M17 14 20 17 17 20 14 17Z" fill="currentColor" strokeWidth={1.5} />
    </svg>
  );
}

/* Self-contained tile. Colors come from classes (see .poko-mark in globals.css)
   so the staff console can swap them without new props. */
export function PokoMark({ size = 28, className = "", ...rest }: P & { size?: number }) {
  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      className={`poko-mark ${className}`}
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      <rect className="tile" width="32" height="32" rx="7" />
      <g
        className="glyph"
        transform="translate(4 4)"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.25}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M5.5 6H11.5V11.5H17V14" />
        <circle cx="5.5" cy="6" r="2.25" fill="currentColor" stroke="none" />
        <path d="M17 14 20 17 17 20 14 17Z" fill="currentColor" strokeWidth={1.5} />
      </g>
    </svg>
  );
}
