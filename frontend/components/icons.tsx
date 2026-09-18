import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

export function GridIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
}

export function LayersIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <path d="M12 2 3 7l9 5 9-5-9-5Z" />
      <path d="M3 12l9 5 9-5" />
      <path d="M3 17l9 5 9-5" />
    </svg>
  );
}

export function CalendarIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <rect x="3" y="4" width="18" height="17" rx="2" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="16" y1="2" x2="16" y2="6" />
    </svg>
  );
}

export function BarChartIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <line x1="4" y1="20" x2="20" y2="20" />
      <rect x="6" y="13" width="3" height="7" />
      <rect x="11" y="8" width="3" height="12" />
      <rect x="16" y="4" width="3" height="16" />
    </svg>
  );
}

export function UploadCloudIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
      <polyline points="8 8 12 4 16 8" />
      <line x1="12" y1="4" x2="12" y2="15" />
    </svg>
  );
}

export function DownloadIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
      <polyline points="8 11 12 15 16 11" />
      <line x1="12" y1="4" x2="12" y2="15" />
    </svg>
  );
}

export function BellIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <path d="M6 8a6 6 0 0 1 12 0c0 4 1.5 5.5 2 6H4c.5-.5 2-2 2-6Z" />
      <path d="M10 21a2 2 0 0 0 4 0" />
    </svg>
  );
}

export function LockIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <rect x="4" y="10" width="16" height="10" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

export function CheckIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

export function XIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

export function AlertTriangleIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <path d="M10.3 3.9 1.9 18a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L14.1 3.9a2 2 0 0 0-3.8 0Z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

export function ClockIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 15.5 14" />
    </svg>
  );
}

export function UsersIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
      <circle cx="10" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

export function FlagIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <path d="M4 21V4a1 1 0 0 1 1-1h11l3 4-3 4H5" />
    </svg>
  );
}

export function ArrowRightIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

export function ChevronDownIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

export function ChevronUpIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <polyline points="18 15 12 9 6 15" />
    </svg>
  );
}

export function FolderPlusIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
      <path d="M12 11v6M9 14h6" />
    </svg>
  );
}

export function FolderIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
    </svg>
  );
}

export function DatabaseIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5" />
      <path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3" />
    </svg>
  );
}

export function GanttIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <line x1="4" y1="6" x2="12" y2="6" />
      <line x1="4" y1="12" x2="18" y2="12" />
      <line x1="4" y1="18" x2="14" y2="18" />
      <circle cx="15" cy="6" r="1.6" />
      <circle cx="21" cy="12" r="1.6" />
      <circle cx="17" cy="18" r="1.6" />
    </svg>
  );
}

export function TrendingUpIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <polyline points="3 17 9 11 13 15 21 6" />
      <polyline points="15 6 21 6 21 12" />
    </svg>
  );
}

export function ShieldCheckIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <path d="M12 2 4 5v6c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V5l-8-3Z" />
      <polyline points="8.5 12 11 14.5 15.5 9.5" />
    </svg>
  );
}

export function DiceIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <rect x="3" y="3" width="18" height="18" rx="3" />
      <circle cx="8" cy="8" r="1.3" />
      <circle cx="16" cy="8" r="1.3" />
      <circle cx="8" cy="16" r="1.3" />
      <circle cx="16" cy="16" r="1.3" />
      <circle cx="12" cy="12" r="1.3" />
    </svg>
  );
}

export function CompareIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <path d="M8 4v14a2 2 0 0 0 2 2h8" />
      <path d="M16 20V6a2 2 0 0 0-2-2H6" />
      <polyline points="5 7 8 4 11 7" />
      <polyline points="19 17 16 20 13 17" />
    </svg>
  );
}

export function BuildingIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <rect x="4" y="10" width="4" height="10" />
      <rect x="10" y="5" width="4" height="15" />
      <rect x="16" y="13" width="4" height="7" />
    </svg>
  );
}

export function SparkleIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <path d="M12 3v5M12 16v5M3 12h5M16 12h5M6 6l3 3M18 18l-3-3M6 18l3-3M18 6l-3 3" />
    </svg>
  );
}

export function ExpandIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <polyline points="15 3 21 3 21 9" />
      <polyline points="9 21 3 21 3 15" />
      <line x1="21" y1="3" x2="14" y2="10" />
      <line x1="3" y1="21" x2="10" y2="14" />
    </svg>
  );
}

export function InfoIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <circle cx="12" cy="12" r="9" />
      <line x1="12" y1="11" x2="12" y2="16" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}

export function SettingsIcon({ className = "icon", ...rest }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" {...rest}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </svg>
  );
}
