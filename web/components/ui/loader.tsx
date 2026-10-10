import { cn } from "@/lib/utils";

// Bar heights echo the coverage map's word-count-proportional blocks.
const BAR_HEIGHTS = [16, 26, 34, 22, 30];

export function Loader({
  className,
  label,
  variant = "bars",
  bars = 5,
}: {
  className?: string;
  label?: string;
  variant?: "bars" | "dots";
  bars?: number;
}) {
  if (variant === "dots") {
    return (
      <span
        className={cn("inline-flex items-center gap-1", className)}
        aria-hidden="true"
      >
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="loader-dot h-1.5 w-1.5 rounded-full bg-accent"
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </span>
    );
  }

  return (
    <div
      className={cn("flex flex-col items-center justify-center gap-3", className)}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-end gap-1.5" aria-hidden="true">
        {Array.from({ length: bars }).map((_, i) => (
          <span
            key={i}
            className="loader-bar w-1.5 rounded-sm bg-accent"
            style={{
              height: BAR_HEIGHTS[i % BAR_HEIGHTS.length],
              animationDelay: `${i * 110}ms`,
            }}
          />
        ))}
      </div>
      {label && <span className="text-body-sm text-text-subtle">{label}</span>}
    </div>
  );
}
