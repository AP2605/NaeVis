import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NaeVis — Autonomous Navigation & Mission Operations",
  description: "GPS-Denied Autonomous Drone Navigation & Multi-Sensor Perception Monitoring Station",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-ops-bg text-ops-text antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}

