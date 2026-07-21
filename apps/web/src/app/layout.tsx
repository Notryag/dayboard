import type { Metadata, Viewport } from "next";
import { QueryProvider } from "./QueryProvider";
import "./globals.css";

const themeInitializer = `
  try {
    const theme = localStorage.getItem("dayboard-theme");
    if (theme === "light" || theme === "dark") {
      document.documentElement.dataset.theme = theme;
    }
  } catch {}
`;

export const metadata: Metadata = {
  title: "Dayboard",
  description: "Plan your day with a conversational scheduling assistant.",
};

export const viewport: Viewport = {
  initialScale: 1,
  viewportFit: "cover",
  width: "device-width",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitializer }} />
      </head>
      <body><QueryProvider>{children}</QueryProvider></body>
    </html>
  );
}
