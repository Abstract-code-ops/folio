import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Folio — Book-first study platform",
  description:
    "A coverage map for your textbooks. See what you know, find what you missed.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-bg-base antialiased">
        {children}
      </body>
    </html>
  );
}
