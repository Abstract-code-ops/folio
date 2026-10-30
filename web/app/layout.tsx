import type { Metadata, Viewport } from "next";
import "./globals.css";
import { ThemeToggle } from "@/components/theme-toggle";
import { DbCallBadge } from "@/components/debug/db-call-badge";
import { caveat } from "@/lib/fonts";

export const metadata: Metadata = {
  title: "Folio — Book-first study platform",
  description:
    "A coverage map for your textbooks. See what you know, find what you missed.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`min-h-screen bg-bg-base antialiased ${caveat.variable}`}>
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{if(localStorage.getItem('folio-theme')==='dark')document.documentElement.classList.add('dark')}catch(e){}",
          }}
        />
        {children}
        <ThemeToggle />
        <DbCallBadge />
      </body>
    </html>
  );
}
