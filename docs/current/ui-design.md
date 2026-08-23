# UI 设计基线

## 目标

Dayboard 是一个仅面向移动端、语音优先的调度工作区，拥有两个同等重要的产品界面：
对话和日视图。它不维护单独的桌面布局或桌面端回退方案。

视觉决策不得散落在各个组件中。颜色、间距、圆角、阴影、排版、控件尺寸和动效都应归属于
全局语义令牌。由单个组件拥有的几何属性应作为该组件根节点上的自定义属性。

## 移动端应用外壳

当前应用外壳如下：

```text
mobile
  -> transparent full-width overlay header with a floating circular view switch
  -> centered Dayboard wordmark without a container
  -> one active full-width view
  -> horizontal content swipe between conversation and schedule
  -> conversation is the default home view
  -> centered voice composer inside the bottom safe area
```

Conversation 在所有视口宽度下都是首页，浮动的页头控件用于在两个全屏顶层区段之间切换。
任务仍位于 Schedule 内。全局页头右侧的控件会打开设置抽屉，用于账户信息、时区、外观、
退出登录和未来的设置。外观支持系统、浅色和深色主题。居中的 wordmark 在文字后方使用
克制的动画渐变光晕。
全局页头覆盖在对话滚动区域之上，并在 Conversation 或 Schedule 内容滚动时保持可见。
它的透明处理保留了全屏界面，不会引入单独的页头色带。
根文档、应用外壳和全屏页面使用相同的界面背景，因此刘海、状态栏、主屏幕指示条以及
过度滚动区域不会显露第二种画布颜色。

移动端视图切换使用 Motion 驱动的可拖拽轨道。界面会一对一地跟随水平输入，然后结合移动
距离和释放速度选择目标，并以可中断、不带弹跳的弹簧动画停靠。Schedule 位于 Conversation
左侧：在 Conversation 中向右拖动会从左侧打开 Schedule，在 Schedule 中向左拖动会返回
Conversation。手势会忽略屏幕外缘、交互控件以及日期轨道等水平滚动区域，因此不会与浏览器
导航或日期浏览竞争。启用减少动效后，将禁用直接拖动，页头控件切换视图时不使用空间动画。
只有当前面板参与焦点处理和无障碍树。当前类似应用的 H5 外壳会将视口锁定为缩放比例 `1`，
以防止在这些全屏界面之间导航时意外触发捏合缩放和焦点缩放。

## 设计方向

Dayboard 应给人以下感受：

- 平静但容易识别
- 精确
- 现代
- 个性化
- 专注工作
- 语音优先

避免：

- 营销式首屏布局
- 将装饰性渐变作为主要身份特征
- 在核心对话可用前先构建大型仪表盘
- 所有内容都使用蓝色、紫色、米色或深石板色的单色调配色
- 在功能组件中硬编码颜色

### 2026 年颜色方向

视觉方向采用冷色、系统中性的画布，并配以鲜明的语义信号。对话界面必须呈现冷白色或
中性灰，绝不能呈现奶油色、米色或暖黄色。实现中的颜色是面向屏幕的产品颜色，并不声称
是专有预报色板的数字等价物。

| 语义角色 | 浅色令牌值 | 产品用途 |
| --- | --- | --- |
| 画布 | `#edf1f5` | 工作界面周围的视口 |
| 界面 | `#f7f8fa` | 主要应用界面 |
| 品牌 / 主要色 | `#087a72` | 选中日期、语音空闲、发送、焦点 |
| AI / 语音活动 | `#d92d7a` | 助手标记、录音状态、活动进度 |
| 日历 | `#4967e8` | 日历条目和议程标记 |
| 任务 | `#9a6700` | 任务和到期状态标记 |
| 成功 | `#16845b` | 已完成和成功状态 |
| 文本 | `#171b18` | 主要可读内容 |

强色应只占界面的一小部分。使用它们表达状态和层级，而不是形成大面积装饰色带。不要添加
渐变、装饰性斑块或随意的彩虹色点缀。

颜色归属保持稳定：

```text
teal     -> brand, selection, primary action, voice idle
fuchsia  -> AI identity and active voice processing
blue     -> calendar entries
amber    -> tasks and deadlines
mint     -> completion and success
red      -> errors and destructive/cancel states only
```

## 令牌

使用 CSS 变量作为第一层设计令牌。将 Dayboard 的 `--dayboard-color-*` 产品令牌映射到
shadcn 主题变量中，使功能 CSS Modules 和共享 UI 原语使用同一个主题，而不是各自维护
并行的配色板。

初始令牌组包括语义颜色、间距、排版、控件尺寸、圆角、焦点、不透明度、阴影和动效：

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

这些值是起点，不是品牌法则。保持名称稳定，以便后续视觉重设计可以修改值，而无需重写组件。

功能样式不得包含原始颜色值。将会随主题变化的决策放入全局语义令牌。将属于单个组件的
几何属性（例如日期单元格宽度或议程时间列宽度）放入该组件根节点的自定义属性中。当 CSS
变量无法表达时，百分比、网格分数和媒体查询条件等结构性 CSS 可以保留为字面值。

## 布局规则

- 仅为移动端 H5 视口设计；不要添加桌面端专用分支或回退布局。
- 对话界面应在 360px 宽度下仍可用。
- 将 Conversation 和 Schedule 保持为独立的全屏移动端视图。
- 将输入栏固定或粘滞在底部。
- 将移动端 composer 放在底部安全区域内。当页头控件负责该导航时，不要在底部标签栏中重复
  Conversation/Schedule 切换。
- 遵守所有移动端安全区域内边距。视口使用 `viewport-fit=cover`；浮动页头、可滚动内容、
  composer 和抽屉都必须让交互内容避开刘海和主屏幕指示条。
- 消息气泡应有稳定的最大宽度，加载时不得造成布局偏移。
- 助手消息使用抬高的中性界面和细微边框。长按仅打开用于真实本地操作的紧凑型、微信风格
  操作菜单：复制和选择文本。按住时移动指针会取消菜单，使对话垂直滚动保持自然。
- 麦克风和发送操作使用带无障碍标签的图标。
- 将调度结果渲染为独立的时间线样式行，而不是将卡片嵌套在结果卡片中。使用窄的日历/任务
  颜色轨道、小型语义图标界面、清晰标题和一行克制的元数据。不要在对话结果中放置完成控件。
- 在带底部安全区域内边距的全宽 bottom sheet 中打开调度条目详情和编辑界面；不要使用居中的
  桌面端对话框。
- 触控目标至少保持 44px。
- 除非当前任务确实需要，否则避免在产品 UI 中加入解释性文字。
- 不要用装饰性卡片包裹页面区段。边框用于划分工作区域；阴影仅用于应用外壳、消息、对话框
  和主要控件。
- 过渡动画只用于颜色、不透明度和小幅变换。日期选择和资源加载不得移动固定格式的导航控件。
- 手势驱动的导航必须直接跟随输入、交接释放速度、保持可中断，并使用空间上对称的返回路径。
  此交互使用 Motion，不使用 CSS keyframes。
- 将多个流式调度结果错开几毫秒，使其到达过程易于辨识，但保持整个序列简短，并在
  `prefers-reduced-motion` 下禁用该效果。

语音是对话首页的默认输入模式，而不是模态框、页面或导航项。主要语音控件是底部的全宽
按住说话栏，沿用熟悉的微信交互形态，但不复制其视觉品牌。录音反馈保留在栏内，键盘切换
仍是其右侧的紧凑图标。它的稳定状态如下：

```text
voice idle   -> neutral "hold to talk" bar, keyboard-mode icon on the right
requesting   -> bar shows microphone permission progress
recording    -> fuchsia bar with live level/timer and a floating cancel target above the composer
transcribing -> upload/provider progress and cancel before command submission
text         -> microphone-mode icon, editable text, send
```

语音命令在转写成功后自动提交；键盘命令仍需要明确执行发送操作。保留已有草稿，将其置于
识别出的语音命令之前。命令完成后，如果语音可用则返回语音模式。在停止、取消或卸载后释放
麦克风轨道、音频上下文、计时器和本地 blob。

录音时，拖动进入可见的胶囊形取消目标只会高亮该目标；在目标内释放会取消，在其他位置释放
会发送。应根据目标实际的屏幕边界判断意图，而不是使用通用的向上距离阈值。目标激活后保留
小幅退出容差，避免手指在边缘附近的轻微移动导致发送和取消之间闪烁切换。

## 组件边界

当前拆分如下：

```text
app/page.tsx                         # route entry only

features/workspace/
  DayboardApp.tsx                    # authenticated workspace composition and navigation
  MobileViewPager.tsx                # measured Motion drag, velocity decision, and spring settling

features/chat/
  useConversationSession.ts          # thread, history, active Run, command, clarification, and undo flow
  ChatMessageList.tsx                # message rendering and clarification placement
  Composer.tsx                       # mode, capabilities, transcription, and errors
  VoiceComposer.tsx                  # hold/release/cancel gestures and recording feedback
  TextComposer.tsx                   # keyboard input, send, and mode switch

features/voice/
  useVoiceRecorder.ts                # MediaRecorder and browser media resource ownership
  api.ts                              # transcription HTTP boundary
```

不要在视觉组件中调用 API。`VoiceComposer` 和 `TextComposer` 只接收状态和回调；提供商调用
通过 `features/voice/api` 保留在 composer 协调器中。

## 状态

对于第一个静态界面，使用本地 React 状态即可。

当命令流程变为真实流程时：

- 使用 TanStack Query 管理服务端命令/Run 状态
- 使用本地 React 状态管理 composer 文本和暂态录音状态
- 仅当状态需要在相距较远的组件之间共享时，才使用 Zustand 或 Jotai

Agent Run 记录、日历条目、任务和转写内容应保持由服务端提供支持。

## 日视图

聚焦的日视图现在是通过共享页头控件选择的一级全屏产品界面。它不是月视图看板，也不是
仪表盘。保持以下稳定区域：

```text
day-view panel
  -> selected weekday / native month-year date picker
  -> horizontally scrollable date rail centered on the selected date
  -> chronological agenda merging calendar entries and dated tasks
  -> separate undated open-task list
```

API 必须使用可信的调度时区解析选中的 `YYYY-MM-DD`。浏览器不得为任意 IANA 时区自行创建
UTC 偏移。仅日期的导航可以使用日历日算术；事件时刻则使用账户 API 返回的时区进行格式化。
当前该时区由服务端配置为 `Asia/Shanghai`；之后可信的租户设置可以替换它。

选中的日期使用语义选择背景。今天未被选中时使用中性界面；不要使用装饰性圆点。初始的
31 天日期轨道从今天位于左边缘开始，使即将到来的日期获得可用空间。滑动会滚动日期轨道，
但不会改变选择；点击单元格才会选中日期。跳转到较远日期时，以该日期为起点创建新的面向
未来的窗口。月份-年份控件保留原生日期选择器，用于较远距离的跳转。

将按时间顺序排列的议程渲染为独立卡片。将每个开始时间标签放置在其卡片之前的垂直空间中，
而不是预留左侧时间列。日历卡片显示持续时长，而不是结束时刻；精确的开始和结束时间仍可在
底部操作表中查看。保持未标日期的任务行紧凑，长标题允许换行，保留 44px 控件，并为每个
数据源独立提供加载、错误、重试和分页状态。日期轨道使用 31 天窗口、CSS scroll snapping
和缓存的 `Intl.DateTimeFormat` 实例；不要为此交互添加 carousel 或 date-picker 依赖。

日历条目和任务在日视图与助手消息之间共享同一个 schedule-item 组件。该组件根据集中管理的
标题关键词选择语义化 Lucide 图标；图标使用语义前景色，不使用装饰性背景块。每张活动卡片
都有单独的右对齐圆形完成控件；卡片的其余部分会打开底部操作表，而不是居中对话框。操作表
展示详情以及垂直排列的编辑、完成和取消操作，编辑时直接替换操作表内容，不再打开另一层。
日历编辑涵盖标题、开始时间和持续时长；任务编辑涵盖标题和可选的到期时间。变更使用整数
`row_version` 作为乐观并发边界；`updated_at` 仅是审计元数据。

直接的圆形完成控件只出现在调度/日视图上下文中。助手确认卡片复用相同的内容和详情操作表，
但省略该控件：新创建的条目应表现为确认，而不是立即提示完成。

组件归属：

```text
SchedulePanel.tsx      # selected date and resource composition
ScheduleHeader.tsx     # weekday and native date picker
DateRail.tsx           # date window, selection, horizontal navigation
DayAgendaSection.tsx   # merged chronological calendar/task display
TaskListSection.tsx    # undated task display
ScheduleItem.tsx       # shared semantic-icon card, details, direct actions
ScheduleItemEditForm.tsx # direct editing and account-timezone conversion
useSchedulePage.ts     # TanStack Query pagination, cache, cancellation, retry
features/reminders     # unread badge, reminder drawer, source navigation, retry
date.ts                # cached display formatters and date-key arithmetic
```

圆形可视化、月/周布局以及浏览器/PWA 推送投递属于后续产品切片。

## 交互与性能验收

- 不要为当前交互添加 carousel 或 date-picker 依赖。原生水平滚动、原生日期输入、CSS Grid
  和 TanStack Query 服务端状态已经足够。
- 点击日期时保持 31 天日期轨道窗口稳定。只有在明确跳转到较远日期，或键盘导航超出当前窗口
  时才重新居中。
- 缓存日期/时间格式化器，并为时间和日期单元格使用表格数字。
- 在加载和活动状态之间保持消息、日期单元格、工具栏和 composer 的尺寸稳定。
- 命令完成后，以及移动端导航返回 Schedule 时，刷新持久化的日视图资源；替换旧的重新挂载
  对话框时不得留下过时的调度数据。
- 遵守 `prefers-reduced-motion`；任何必要状态都不得依赖动画。
- 在 390x844 和 1280x800 下验证。不得出现水平溢出、控件重叠、空白面板，或以页面滚动替代
  面板滚动的情况。
- 发布前在浅色和深色配色方案中验证文本与图标的对比度。
