import { formatDate, timeAgo } from "@/lib/utils";
import type { ReactNode } from "react";

interface Props {
  value: string;
  prefix?: ReactNode;
}

export function RelativeTime({ value, prefix }: Props) {
  const relative = timeAgo(value);
  if (!relative) return null;
  return (
    <>
      {prefix}
      <time dateTime={value} title={formatDate(value)}>{relative}</time>
    </>
  );
}
