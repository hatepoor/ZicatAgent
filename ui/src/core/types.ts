// 前端领域类型：只描述内核协议与视图数据，不含任何业务逻辑。
import type { Theme } from "../themes";

export type RpcUsage = {
  requests?: number;
  input?: number;
  output?: number;
  last_input?: number;
  input_per_request?: number;
};

export type RpcCommand = { cmd: string; desc: string };

export type SessionItem = {
  thread_id: string;
  title: string;
  workspace_dir: string;
  workspace?: string;
  updated_at?: string;
  status?: string;
};

export type HistoryItem = {
  kind: "user" | "assistant" | "tool";
  text?: string;
  name?: string;
  args?: string;
  status?: string;
  payload?: Record<string, unknown> | null;
};

export type ModelConfig = {
  index: number;
  env_index?: number;
  name: string;
  model: string;
  base_url: string;
  api_key: string;
  context_window?: string | number;
  max_tokens?: string | number;
  temperature?: string | number;
};

export type RpcEvent = {
  event: string;
  call_id?: string;
  payload?: Record<string, unknown> | null;
  text?: string;
  name?: string;
  args?: string;
  ok?: boolean;
  question?: string;
  candidates?: string[];
  usage?: RpcUsage;
  requests?: number;
  input?: number;
  output?: number;
  last_input?: number;
  input_per_request?: number;
  engine?: string;
  model?: string;
  cwd?: string;
  commands?: RpcCommand[];
  models?: ModelConfig[];
  active?: number;
  index?: number;
  workspace?: string;
  workspace_root?: string;
  default_workspace?: string;
  path?: string;
  root?: string;
  context_char_cap?: number;
  changed?: boolean;
  session?: string;
  sessions?: SessionItem[];
  workspaces?: string[];
  thread_id?: string;
  active_thread_id?: string;
  active_workspace?: string;
  record?: SessionItem;
  history?: HistoryItem[];
};

export type SendMsg =
  | { type: "task"; text: string }
  | { type: "answer"; text: string }
  | { type: "abort" }
  | { type: "exit" }
  | { type: "get_models"; reveal?: boolean }
  | { type: "save_model"; index: number; config: Record<string, string> }
  | { type: "set_model"; index: number }
  | { type: "get_workspace" }
  | { type: "set_workspace"; path: string }
  | { type: "get_sessions" }
  | { type: "get_history"; thread_id?: string }
  | { type: "new_session" }
  | { type: "switch_session"; thread_id: string }
  | { type: "delete_session"; thread_id: string }
  | { type: "delete_workspace"; path: string };

export type EntryStatus = "running" | "done" | "error";

export type Entry =
  | { id: number; kind: "user"; text: string }
  | {
      id: number;
      kind: "assistant";
      text: string;
      shown: number;
      done: boolean;
      summary?: string;
      raw?: string;
    }
  | {
      id: number;
      kind: "tool";
      name: string;
      args: string;
      lines: string[];
      status: EntryStatus;
      duration?: number;
      payload?: Record<string, unknown> | null;
    }
  | { id: number; kind: "system"; text: string }
  | { id: number; kind: "interrupt"; question: string; candidates: string[]; answered?: boolean }
  | { id: number; kind: "error"; text: string };

export type PendingDelete =
  | { kind: "session"; session: SessionItem }
  | { kind: "workspace"; workspace: string; count: number }
  | null;

export type ThemeState = {
  theme: Theme;
  options: Theme[];
  themeIdx: number;
  setThemeIdx: (index: number) => void;
  menu: boolean;
  setMenu: (open: boolean) => void;
  next: () => void;
};
