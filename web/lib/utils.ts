import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a coverage score (0–15) into its visual state label.
 */
export function coverageStateLabel(score: number): string {
  if (score <= 0) return "Not started";
  if (score <= 4) return "Mentioned";
  if (score <= 9) return "Partial";
  return "Well covered";
}
