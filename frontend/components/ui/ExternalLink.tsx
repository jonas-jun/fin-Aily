import type { AnchorHTMLAttributes, PropsWithChildren } from "react";

type Props = PropsWithChildren<AnchorHTMLAttributes<HTMLAnchorElement>>;

export function ExternalLink({ children, ...props }: Props) {
  return (
    <a {...props} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}
