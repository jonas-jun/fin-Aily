import Link from "next/link";

interface Props {
  size?: "sm" | "lg";
}

function TriangleI() {
  return (
    <span className="relative inline-block">
      <span>ı</span>
      <svg
        viewBox="0 0 10 9"
        className="absolute fill-[#22C55E]"
        style={{ width: "0.38em", left: "50%", transform: "translateX(-50%)", top: "0.06em" }}
        aria-hidden="true"
      >
        <polygon points="5,0 10,9 0,9" />
      </svg>
    </span>
  );
}

export function Logo({ size = "sm" }: Props) {
  const textCls = size === "lg" ? "text-5xl" : "text-[22px]";
  const badgeCls =
    size === "lg"
      ? "text-lg px-2.5 py-1 rounded-md ml-2"
      : "text-[11px] px-1.5 py-[3px] rounded ml-1.5";

  return (
    <Link
      href="/"
      className="inline-flex items-center shrink-0 select-none"
      aria-label="fin-aily-us"
    >
      <span
        className={`font-extrabold ${textCls} text-[#1E3A5F] tracking-tight leading-none`}
      >
        f<TriangleI />n-a<TriangleI />ly
      </span>
      <span
        className={`bg-[#22C55E] text-white font-extrabold ${badgeCls} leading-none`}
      >
        US
      </span>
    </Link>
  );
}
