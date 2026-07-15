# UI Design Baseline

## Goal

Dayboard is a voice-first scheduling workspace with two equal product surfaces: conversation and the
day view. It must remain efficient on a phone while using desktop space as a real work area rather
than rendering a phone-shaped demo in the center of the viewport.

Visual decisions must not be scattered through components. Colors, spacing, radius, shadows,
typography, control sizes, and motion belong in global semantic tokens. Geometry owned by one
component belongs in custom properties on that component root.

## Responsive App Shell

The current application shell is:

```text
mobile (< 900px)
  -> compact brand/date header
  -> one active full-width view
  -> conversation is the default home view
  -> centered voice composer above navigation
  -> persistent floating-glass Conversation / Schedule tab bar

desktop (>= 900px)
  -> full-height work surface, maximum width 1280px
  -> compact shared brand/account header
  -> conversation pane on the left
  -> persistent day-view pane on the right
```

The desktop layout is a two-pane operational tool, not a dashboard of cards. On mobile, conversation
is the home page and a bottom tab bar switches only between the two top-level sections. Tasks remain
inside Schedule; account settings remain in the header.

## Design Direction

Dayboard should feel:

- calm but recognizable
- precise
- modern
- personal
- work-focused
- voice-first

Avoid:

- marketing-style hero layouts
- decorative gradients as the main identity
- large dashboards before the core conversation works
- one-hue palettes where everything is blue, purple, beige, or dark slate
- hard-coded colors inside feature components

### 2026 Color Direction

The visual direction uses a cool system-neutral canvas with vivid semantic signals. Conversation
surfaces must read as cool white or neutral gray, never cream, beige, or warm yellow. The
implementation colors are screen-oriented product colors, not claimed digital equivalents of
proprietary forecast swatches.

| Semantic role | Light token value | Product use |
| --- | --- | --- |
| canvas | `#edf1f5` | viewport around the work surface |
| surface | `#f7f8fa` | primary application surface |
| brand / primary | `#087a72` | selected dates, voice idle, send, focus |
| AI / voice activity | `#d92d7a` | assistant mark, recording state, active progress |
| calendar | `#4967e8` | calendar entries and agenda markers |
| task | `#9a6700` | tasks and due-state markers |
| success | `#16845b` | completed and successful states |
| text | `#171b18` | primary readable content |

Strong colors should occupy a minority of the interface. Use them for state and hierarchy, not as
large decorative bands. Do not add gradients, decorative blobs, or arbitrary rainbow accents.

Color ownership is stable:

```text
teal     -> brand, selection, primary action, voice idle
fuchsia  -> AI identity and active voice processing
blue     -> calendar entries
amber    -> tasks and deadlines
mint     -> completion and success
red      -> errors and destructive/cancel states only
```

## Tokens

Use CSS variables as the first design-token layer. If shadcn/ui is installed, map these concepts to the shadcn theme variables instead of inventing a parallel theme.

Initial token groups include semantic colors, spacing, typography, control sizing, radii, focus,
opacity, shadows, and motion:

```css
:root {
  --color-bg: #edf1f5;
  --color-surface: #f7f8fa;
  --color-surface-raised: #ffffff;
  --color-surface-muted: #eef1f5;
  --color-text: #181a1d;
  --color-text-muted: #68717c;
  --color-border: #d9dfe7;

  --color-primary: #087a72;
  --color-primary-foreground: #ffffff;
  --color-primary-surface: #e2f3ef;
  --color-accent: #d92d7a;
  --color-calendar: #4967e8;
  --color-task: #9a6700;
  --color-success: #16845b;

  --message-user-bg: var(--color-primary);
  --message-user-text: #ffffff;
  --message-assistant-bg: #ffffff;
  --message-assistant-text: var(--color-text);

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;

  --font-size-caption: 12px;
  --font-size-label: 13px;
  --font-size-ui: 14px;
  --font-size-body: 15px;
  --font-size-title: 19px;
  --control-size: 44px;

  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-pill: 999px;

  --shadow-soft: 0 24px 70px rgb(26 57 45 / 11%);
}
```

These values are starting points, not brand law. Keep the names stable so later visual redesigns can change values without rewriting components.

Feature styles must not contain raw color values. Put theme-changing decisions in global semantic
tokens. Put geometry that belongs to one component, such as date-cell width or agenda time-column
width, in custom properties on that component's root. Structural CSS such as percentages, grid
fractions, and media-query conditions may remain literal when CSS variables cannot express them.

## Layout Rules

- Design mobile first, then expand carefully for desktop.
- The conversation screen should be usable at 360px width.
- Switch to the persistent two-pane workspace at 900px; do not squeeze two panes onto tablets.
- Keep the desktop work surface at or below 1280px and give both panes independent scrolling.
- Keep the input dock fixed or sticky at the bottom.
- Keep the mobile tab bar below the input dock and inside the bottom safe area. It is a floating,
  translucent system control with background blur, a light glass border, and restrained elevation.
  Use icon-above-label tabs, selected tint, and no underline or selected background capsule.
- Respect mobile safe-area insets.
- Message bubbles should have stable max widths and must not shift layout while loading.
- Assistant messages use a raised neutral surface and subtle border. A long press opens a compact,
  WeChat-style action menu for real local actions only: copy and select text. Moving the pointer
  while pressing cancels the menu so vertical conversation scrolling remains natural.
- Use icons for microphone and send actions, with accessible labels.
- Keep touch targets at least 44px.
- Avoid explanatory text in the product UI unless it is necessary for the current task.
- Do not wrap page sections in decorative cards. Borders divide work regions; shadows are reserved
  for the application shell, messages, dialogs, and primary controls.
- Use transitions only for color, opacity, and small transforms. Date selection and resource loading
  must not move fixed-format navigation controls.

Voice is the conversation home's default input mode rather than a modal, page, or navigation item.
The primary voice control is a full-width hold-to-talk bar above the tab bar, following the familiar
WeChat interaction shape without copying its visual branding. Recording feedback stays inside the
bar and the keyboard switch remains a compact icon on its right. Its stable states are:

```text
voice idle   -> neutral "hold to talk" bar, keyboard-mode icon on the right
requesting   -> bar shows microphone permission progress
recording    -> fuchsia bar with live level/timer, slide up to cancel, release to send
transcribing -> upload/provider progress and cancel before command submission
text         -> microphone-mode icon, editable text, send
```

Voice commands submit automatically after successful transcription; keyboard commands still require
an explicit send action. Preserve an existing draft by prepending it to the recognized voice command.
After a completed command, return to voice mode when voice is available. Release microphone tracks,
audio contexts, timers, and local blobs after stop, cancel, or unmount.

## Component Boundaries

Current split:

```text
app/page.tsx             # conversation command state and responsive view selection

features/chat/
  ChatMessageList.tsx   # message rendering and clarification placement
  Composer.tsx          # mode, capabilities, transcription, and errors
  VoiceComposer.tsx     # hold/release/cancel gestures and recording feedback
  TextComposer.tsx      # keyboard input, send, and mode switch

features/voice/
  useVoiceRecorder.ts   # MediaRecorder and browser media resource ownership
  api.ts                # transcription HTTP boundary
```

Keep API calls out of visual components. `VoiceComposer` and `TextComposer` receive state and
callbacks only; provider calls stay in the composer coordinator through `features/voice/api`.

## State

For the first static screen, local React state is enough.

When the command flow becomes real:

- use TanStack Query for server-backed command/run state
- use local React state for composer text and transient recording state
- use Zustand or Jotai only when state needs to be shared across distant components

Agent run records, calendar entries, tasks, and transcripts should remain server-backed.

## Day View

The focused day view is now a first-level product surface: persistent on desktop and selected through
the mobile Schedule tab. It is not a month board or a dashboard. Keep these stable regions:

```text
day-view panel
  -> selected weekday / native month-year date picker
  -> horizontally scrollable date rail centered on the selected date
  -> chronological agenda merging calendar entries and dated tasks
  -> separate undated open-task list
```

The API must interpret a selected `YYYY-MM-DD` using the trusted scheduling timezone. The browser must
not invent UTC offsets for arbitrary IANA timezones. Date-only navigation can use calendar-day
arithmetic; event instants are formatted in the timezone returned by the account API. This is
currently server-configured `Asia/Shanghai`; a trusted tenant setting may replace it later.

The selected date uses the semantic selection background. Today uses a neutral surface when it is
not selected; do not use a decorative dot. The initial 31-day rail starts with today at the left edge
so upcoming dates receive the available space. Swiping scrolls the rail but does not change
selection; tapping a cell selects it. A distant date jump starts a new forward-looking window at that
date. The month-year control retains the native date picker for distant jumps.

Render the chronological agenda as separate cards. Place each start-time label in the vertical space
before its card instead of reserving a left-hand time column. Calendar cards show duration rather
than an end clock time; exact start and end times remain available in the bottom action sheet. Keep undated
task rows compact, wrap long titles, preserve 44px controls, and give each source independent loading,
error, retry, and pagination state. The date rail uses a 31-day window, CSS scroll snapping, and
cached `Intl.DateTimeFormat` instances; do not add a carousel or date-picker dependency for this
interaction.

Calendar entries and tasks share one schedule-item component across the day view and assistant
messages. It chooses a semantic Lucide icon from centralized title keywords; icons use semantic
foreground colors without decorative background tiles. Each active card has a separate right-aligned
circular completion control; the rest of the card opens a bottom action sheet instead of a centered
dialog. The sheet presents details and vertical edit, complete, and cancel actions, and editing
replaces the sheet body without opening another layer. Calendar editing covers title, start time,
and duration; task editing covers title and optional due time. Mutations use `updated_at` as an
optimistic-concurrency boundary.

Component ownership:

```text
SchedulePanel.tsx      # selected date and resource composition
ScheduleHeader.tsx     # weekday and native date picker
DateRail.tsx           # date window, selection, horizontal navigation
DayAgendaSection.tsx   # merged chronological calendar/task display
TaskListSection.tsx    # undated task display
ScheduleItem.tsx       # shared semantic-icon card, details, direct actions
ScheduleItemEditForm.tsx # direct editing and account-timezone conversion
useSchedulePage.ts     # pagination, stale-request cancellation, retry
date.ts                # cached display formatters and date-key arithmetic
```

Circular visualization, month/week layouts, and reminder delivery UI are later product slices.

## Interaction And Performance Acceptance

- Do not add a carousel, date-picker, animation, or state-management dependency for the current
  interactions. Native horizontal scrolling, native date input, CSS Grid, and local state are enough.
- Keep the 31-day rail window stable when a date is tapped. Recenter only after an explicit distant
  date jump or keyboard navigation beyond the current window.
- Cache date/time formatters and use tabular numerals for times and date cells.
- Keep message, date-cell, toolbar, and composer dimensions stable across loading and active states.
- Refresh the persistent day-view resources after a command completes and when mobile navigation
  returns to Schedule; replacing the old remounting dialog must not leave stale schedule data.
- Honor `prefers-reduced-motion`; no essential state may depend on animation.
- Validate at 390x844 and 1280x800. There must be no horizontal overflow, overlapping controls,
  blank panels, or page-level scrolling in place of pane scrolling.
- Verify text and icon contrast in both light and dark color schemes before release.
