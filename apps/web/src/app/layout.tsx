import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Dayboard",
  description: "Plan your day with a conversational scheduling assistant.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
