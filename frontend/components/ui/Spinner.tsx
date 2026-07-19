interface Props {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const sizeClasses = {
  sm: "h-6 w-6 border-2",
  md: "h-8 w-8 border-2",
  lg: "h-12 w-12 border-4",
};

export function Spinner({ size = "md", className = "" }: Props) {
  return (
    <span
      className={`${sizeClasses[size]} inline-block animate-spin rounded-full border-green-100 border-t-brand-green ${className}`}
      aria-hidden
    />
  );
}
