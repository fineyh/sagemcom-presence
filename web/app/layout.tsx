import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sagemcom Presence",
  description: "Who is on my network — live status and history",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
