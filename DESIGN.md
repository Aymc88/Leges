# Leges Design System

## Palette

| Role       | Hex       | Usage                                 |
|------------|-----------|---------------------------------------|
| Background | `#37123C` | Page background                       |
| Text       | `#D1CCC7` | Primary text, completed step dots     |
| Buttons    | `#DDA77B` | Primary buttons, active sidebar item  |
| Secondary  | `#71677C` | Highlight / accent                    |
| Highlight  | `#945D5E` | Progress bars, teal buttons, accents  |

## CSS Variables

```css
--bg:            #37123C;
--surface:       #44204A;
--text:          #D1CCC7;
--text-secondary:#A9989E;
--border:        #523757;
--blue:          #DDA77B;
--teal:          #945D5E;
--sidebar-bg:    #2A0E2E;
--sidebar-hover: #44204A;
--sidebar-active:#DDA77B;
--shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
```

## Typography

- Font stack: `system-ui, -apple-system, sans-serif`
- Weight 800 for headings, 600 for buttons, 500 for nav items
- Card titles: 12px uppercase with letter-spacing

## Components

### Sidebar
- Darker purple (`#2A0E2E`) background with white text at 85% opacity
- Active item: warm peach (`#DDA77B`) background, white text
- Hover item: lighter purple (`#44204A`) background

### Cards
- Slightly lighter purple (`#44204A`) background to distinguish from page
- Subtle border (`#523757`)
- Box shadow: `0 1px 3px rgba(0, 0, 0, 0.3)`

### Buttons
- Primary: warm peach `#DDA77B` background, white text
- Secondary: `#44204A` background, `#523757` border, `#A9989E` text
- Teal/accent: muted mahogany `#945D5E` background, white text

### Progress Bars
- Fill: `#945D5E` (highlight)
- Track: `#523757` (border color)

### Step Dots
- Active: `#DDA77B` (button color)
- Completed: `#D1CCC7` (text color)
- Inactive: `#C4BFBA` (light warm gray)
