# UI Design Baseline

## Goal

Dayboard should start with the smallest useful interface: a mobile-first conversation screen.

The UI will likely change significantly later, so the first implementation should avoid hard-coded visual decisions scattered through components. Put colors, spacing, radius, shadows, and typography into CSS variables or theme tokens from the start.

## First Screen

Phase 1 should render:

```text
mobile viewport
  -> top safe area / app title
  -> conversation history
  -> assistant and user message bubbles
  -> bottom input dock
  -> text input
  -> voice button
  -> send button
```

Do not build calendar boards, dashboards, sidebars, or task panels until the command loop works.

## Design Direction

Dayboard should feel:

- calm
- precise
- lightweight
- personal
- work-focused

Avoid:

- marketing-style hero layouts
- decorative gradients as the main identity
- large dashboards before the core conversation works
- one-hue palettes where everything is blue, purple, beige, or dark slate
- hard-coded colors inside feature components

## Tokens

Use CSS variables as the first design-token layer. If shadcn/ui is installed, map these concepts to the shadcn theme variables instead of inventing a parallel theme.

Initial token groups:

```css
:root {
  --color-bg: #f3f3f2;
  --color-surface: #fafafa;
  --color-surface-raised: #ffffff;
  --color-text: #111111;
  --color-text-muted: #6b6b68;
  --color-border: #d8d8d4;

  --color-primary: #111111;
  --color-primary-foreground: #ffffff;
  --color-accent: #292927;
  --color-warning: #555552;
  --color-danger: #3b3b39;

  --message-user-bg: #111111;
  --message-user-text: #ffffff;
  --message-assistant-bg: #ffffff;
  --message-assistant-text: #111111;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;

  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-pill: 999px;

  --shadow-soft: 0 14px 36px rgb(0 0 0 / 9%);
}
```

These values are starting points, not brand law. Keep the names stable so later visual redesigns can change values without rewriting components.

## Layout Rules

- Design mobile first, then expand carefully for desktop.
- The conversation screen should be usable at 360px width.
- Keep the input dock fixed or sticky at the bottom.
- Respect mobile safe-area insets.
- Message bubbles should have stable max widths and must not shift layout while loading.
- Use icons for microphone and send actions, with accessible labels.
- Keep touch targets at least 44px.
- Avoid explanatory text in the product UI unless it is necessary for the current task.

## Component Boundaries

Recommended first split:

```text
features/chat/
  ChatShell.tsx
  MessageList.tsx
  MessageBubble.tsx
  Composer.tsx
```

Keep API calls out of visual components. When the backend command endpoint exists, route calls through `lib/api` or a feature hook.

## State

For the first static screen, local React state is enough.

When the command flow becomes real:

- use TanStack Query for server-backed command/run state
- use local React state for composer text and transient recording state
- use Zustand or Jotai only when state needs to be shared across distant components

Agent run records, calendar entries, tasks, and transcripts should remain server-backed.
