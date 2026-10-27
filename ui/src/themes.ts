export interface Theme {
  id: string;
  label: string;
  bg: string;
  bgGlow: string;
  panel: string;
  panelSoft: string;
  border: string;
  fg: string;
  dim: string;
  faint: string;
  accent: string;
  accent2: string;
  green: string;
  yellow: string;
  red: string;
  blue: string;
  magenta: string;
  cyan: string;
  selection: string;
}

export const THEMES: Theme[] = [
  {
    id: "tokyo",
    label: "Tokyo Night",
    bg: "#13141c",
    bgGlow: "#1a1b26",
    panel: "#16161e",
    panelSoft: "#1f2335",
    border: "#2c2e44",
    fg: "#c0caf5",
    dim: "#787fa8",
    faint: "#3b3f58",
    accent: "#7aa2f7",
    accent2: "#bb9af7",
    green: "#9ece6a",
    yellow: "#e0af68",
    red: "#f7768e",
    blue: "#7aa2f7",
    magenta: "#bb9af7",
    cyan: "#7dcfff",
    selection: "#2d3150",
  },
  {
    id: "catppuccin",
    label: "Catppuccin Mocha",
    bg: "#171720",
    bgGlow: "#1e1e2e",
    panel: "#181825",
    panelSoft: "#242438",
    border: "#313147",
    fg: "#cdd6f4",
    dim: "#8a8fae",
    faint: "#3f3f58",
    accent: "#cba6f7",
    accent2: "#f5c2e7",
    green: "#a6e3a1",
    yellow: "#f9e2af",
    red: "#f38ba8",
    blue: "#89b4fa",
    magenta: "#cba6f7",
    cyan: "#94e2d5",
    selection: "#31324a",
  },
  {
    id: "gruvbox",
    label: "Gruvbox Dark",
    bg: "#1d2021",
    bgGlow: "#282828",
    panel: "#212526",
    panelSoft: "#32302f",
    border: "#3f3c3a",
    fg: "#ebdbb2",
    dim: "#a89984",
    faint: "#504945",
    accent: "#fabd2f",
    accent2: "#fe8019",
    green: "#b8bb26",
    yellow: "#fabd2f",
    red: "#fb4934",
    blue: "#83a598",
    magenta: "#d3869b",
    cyan: "#8ec07c",
    selection: "#3c3836",
  },
  {
    id: "matrix",
    label: "Matrix",
    bg: "#050a06",
    bgGlow: "#0a120b",
    panel: "#071009",
    panelSoft: "#0d1b10",
    border: "#15371d",
    fg: "#9dffb0",
    dim: "#3f8a50",
    faint: "#174423",
    accent: "#39ff6e",
    accent2: "#00e5a0",
    green: "#39ff6e",
    yellow: "#d6ff5c",
    red: "#ff5c5c",
    blue: "#55d7ff",
    magenta: "#8dffcf",
    cyan: "#55ffd7",
    selection: "#103a1a",
  },
];
