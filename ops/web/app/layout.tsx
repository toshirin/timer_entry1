import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Timer Entry Ops",
  description: "Runtime monitoring dashboard"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
