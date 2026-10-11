import { Caveat } from "next/font/google";

// Handwriting font for margin notes + signature (docs/note-section.md).
export const caveat = Caveat({
  subsets: ["latin"],
  variable: "--font-hand",
  display: "swap",
});
