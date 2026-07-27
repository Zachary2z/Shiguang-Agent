import type { SVGProps } from "react";

export type IconName = "agent" | "collections" | "plans" | "me" | "spark";

export function Icon({
  name,
  ...props
}: SVGProps<SVGSVGElement> & { name: IconName }) {
  const paths: Record<IconName, React.ReactNode> = {
    agent: (
      <>
        <path d="M4 12a8 8 0 1 1 3.1 6.3L3 21l1.3-4.8A8 8 0 0 1 4 12Z" />
        <path d="M8.5 12h.01M12 12h.01M15.5 12h.01" />
      </>
    ),
    collections: (
      <>
        <path d="M6 3h12a2 2 0 0 1 2 2v14l-8-4-8 4V5a2 2 0 0 1 2-2Z" />
        <path d="M8 7h8" />
      </>
    ),
    plans: (
      <>
        <path d="M6 3v3M18 3v3M4 8h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z" />
        <path d="m8 14 2 2 5-5" />
      </>
    ),
    me: (
      <>
        <circle cx="12" cy="8" r="4" />
        <path d="M4.5 21a7.5 7.5 0 0 1 15 0" />
      </>
    ),
    spark: (
      <path d="m12 2 1.4 5.1L18 10l-4.6 2.9L12 18l-1.4-5.1L6 10l4.6-2.9L12 2Z" />
    ),
  };

  return (
    <svg
      aria-hidden="true"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}
