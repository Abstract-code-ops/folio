import { cn } from "@/lib/utils";

// Warm paper surface with the generated grain (see .paper in globals.css).
export function PaperSurface({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("paper bg-bg-surface", className)}>{children}</div>;
}
