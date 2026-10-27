import { useCallback, useEffect, useRef, useState } from "react";
import { connect, send } from "../api";
import { BLOCKED_COMMANDS } from "../core/config";
import { historyToEntries } from "../core/history";
import { cleanAssistant, extractSummary, stripInternal } from "../core/text";
import type {
  Entry,
  ModelConfig,
  PendingDelete,
  RpcCommand,
  RpcEvent,
  SessionItem,
} from "../core/types";

type Options = {
  onTheme?: () => void;
};

/**
 * Agent 会话深模块：封装 RPC 连接、流事件状态机、会话/模型/工作区动作。
 * 组件只消费返回的只读状态与动作，不直接触碰 EventSource 或协议细节。
 */
export function useAgentSession(options: Options = {}) {
  const onTheme = options.onTheme;
  const [entries, setEntries] = useState<Entry[]>([]);
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [model, setModel] = useState("连接中…");
  const [cwd, setCwd] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [workspaceRoot, setWorkspaceRoot] = useState("");
  const [defaultWorkspace, setDefaultWorkspace] = useState("");
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [activeModel, setActiveModel] = useState(0);
  const [modal, setModal] = useState<"model" | "workspace" | null>(null);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete>(null);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [workspaces, setWorkspaces] = useState<string[]>([]);
  const [activeThreadId, setActiveThreadId] = useState("");
  const [kernelCommands, setKernelCommands] = useState<RpcCommand[]>([]);
  const [usageTotal, setUsageTotal] = useState({ requests: 0, input: 0, output: 0 });
  const [contextTokens, setContextTokens] = useState(0);
  const [contextCharCap, setContextCharCap] = useState(0);
  const [startedAt, setStartedAt] = useState(() => Date.now());

  const idRef = useRef(0);
  const nextId = useCallback(() => ++idRef.current, []);
  const openAssistant = useRef<number | null>(null);
  const openTools = useRef<{ id: number; name: string; callId?: string; t0: number }[]>([]);
  const assistantHadText = useRef(false);
  const lastWasSlash = useRef(false);
  const busyRef = useRef(false);
  const exitedRef = useRef(false);
  const esRef = useRef<EventSource | null>(null);
  const entriesRef = useRef(0);

  useEffect(() => {
    entriesRef.current = entries.length;
  }, [entries]);

  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);

  const push = useCallback((entry: Entry) => {
    setEntries((prev) => [...prev, entry]);
  }, []);

  const patch = useCallback((id: number, fn: (entry: Entry) => Entry) => {
    setEntries((prev) => prev.map((entry) => (entry.id === id ? fn(entry) : entry)));
  }, []);

  const closeAssistant = useCallback(() => {
    const id = openAssistant.current;
    if (id != null) {
      patch(id, (entry) => (entry.kind === "assistant" ? { ...entry, done: true } : entry));
      openAssistant.current = null;
    }
  }, [patch]);

  const clearChat = useCallback(() => {
    setEntries([]);
    openAssistant.current = null;
    openTools.current = [];
    assistantHadText.current = false;
  }, []);

  const resetUi = useCallback(() => {
    clearChat();
    setUsageTotal({ requests: 0, input: 0, output: 0 });
    setContextTokens(0);
    setStartedAt(Date.now());
    setBusy(false);
  }, [clearChat]);

  const doAbort = useCallback(() => {
    if (!busyRef.current) return;
    closeAssistant();
    void send({ type: "abort" }).catch(() => undefined);
  }, [closeAssistant]);

  const pushSystem = useCallback(
    (text: string) => push({ id: nextId(), kind: "system", text }),
    [push, nextId],
  );

  const handleEvent = useCallback(
    (event: RpcEvent) => {
      switch (event.event) {
        case "ready":
          setModel(event.model || "?");
          setCwd(event.cwd || "");
          setWorkspace(event.workspace || "");
          setWorkspaceRoot(event.workspace_root || "");
          setDefaultWorkspace(event.default_workspace || "");
          setModels(event.models || []);
          setActiveModel(event.active ?? 0);
          setContextCharCap(Number(event.context_char_cap) || 0);
          setSessions(event.sessions || []);
          setWorkspaces(event.workspaces || []);
          setActiveThreadId(event.thread_id || "");
          setKernelCommands(event.commands || []);
          setConnected(true);
          exitedRef.current = false;
          {
            const last = Number(event.usage?.last_input || event.usage?.input_per_request || 0);
            if (last > 0) setContextTokens(last);
          }
          if (event.history?.length) {
            setEntries((prev) =>
              prev.length ? prev : historyToEntries(event.history || [], nextId),
            );
          }
          void send({ type: "get_sessions" }).catch(() => undefined);
          break;
        case "sessions":
          setSessions(event.sessions || []);
          setWorkspaces(event.workspaces || []);
          if (typeof event.active_thread_id === "string") {
            setActiveThreadId(event.active_thread_id);
          }
          if (event.active_workspace) setWorkspace(event.active_workspace);
          {
            const last = Number(event.usage?.last_input || event.usage?.input_per_request || 0);
            if (last > 0) setContextTokens(last);
          }
          if (event.active_thread_id && entriesRef.current === 0) {
            void send({ type: "get_history", thread_id: event.active_thread_id })
              .catch(() => undefined);
          }
          break;
        case "session_new":
          resetUi();
          setSessions(event.sessions || []);
          setWorkspaces(event.workspaces || []);
          setActiveThreadId("");
          setWorkspace((prev) => event.active_workspace || prev);
          break;
        case "session_switched":
          resetUi();
          setSessions(event.sessions || []);
          setWorkspaces(event.workspaces || []);
          setEntries(historyToEntries(event.history || [], nextId));
          setActiveThreadId(event.record?.thread_id || event.active_thread_id || "");
          setWorkspace((prev) => event.active_workspace || event.record?.workspace_dir || prev);
          {
            const last = Number(event.usage?.last_input || event.usage?.input_per_request || 0);
            if (last > 0) setContextTokens(last);
          }
          break;
        case "history":
          if (event.history) setEntries(historyToEntries(event.history, nextId));
          break;
        case "models":
          setModels(event.models || []);
          if (typeof event.active === "number") setActiveModel(event.active);
          if (typeof event.context_char_cap === "number") {
            setContextCharCap(event.context_char_cap);
          }
          {
            const idx = typeof event.active === "number" ? event.active : 0;
            const current = (event.models || [])[idx];
            if (current?.model) setModel(current.model);
          }
          break;
        case "model_switched": {
          const idx = typeof event.index === "number" ? event.index : (event.active ?? 0);
          setActiveModel(idx);
          setModel(event.model || "?");
          pushSystem(
            `模型已切换 → ${event.name || event.model || "?"}（下个任务生效）`,
          );
          break;
        }
        case "workspace":
          setWorkspace(event.workspace || event.path || "");
          if (event.workspace_root || event.root) {
            setWorkspaceRoot(event.workspace_root || event.root || "");
          }
          if (event.default_workspace) setDefaultWorkspace(event.default_workspace);
          break;
        case "delta": {
          const chunk = event.text || "";
          if (!chunk) break;
          const id = openAssistant.current;
          if (id != null) {
            patch(id, (entry) => {
              if (entry.kind !== "assistant") return entry;
              const raw = (entry.raw || "") + chunk;
              const text = cleanAssistant(raw);
              if (text) assistantHadText.current = true;
              return { ...entry, raw, text, summary: extractSummary(raw) || entry.summary };
            });
          } else {
            const text = cleanAssistant(chunk);
            if (text) assistantHadText.current = true;
            const nid = nextId();
            openAssistant.current = nid;
            push({
              id: nid,
              kind: "assistant",
              text,
              shown: 0,
              done: false,
              raw: chunk,
              summary: extractSummary(chunk),
            });
          }
          break;
        }
        case "tool_call": {
          closeAssistant();
          const nid = nextId();
          openTools.current.push({
            id: nid,
            name: event.name || "",
            callId: event.call_id,
            t0: Date.now(),
          });
          push({
            id: nid,
            kind: "tool",
            name: event.name || "",
            args: event.args || "",
            lines: [],
            status: "running",
          });
          break;
        }
        case "tool_result": {
          const list = openTools.current;
          let idx = event.call_id
            ? list.findIndex((item) => item.callId === event.call_id)
            : -1;
          if (idx < 0) idx = list.findIndex((item) => item.name === (event.name || ""));
          if (idx < 0 && list.length > 0) idx = 0;
          const tool = idx >= 0 ? list[idx] : undefined;
          if (tool) {
            list.splice(idx, 1);
            patch(tool.id, (entry) =>
              entry.kind === "tool"
                ? {
                    ...entry,
                    lines: (event.text || "").split("\n"),
                    payload: event.payload ?? null,
                    status: event.ok === false ? "error" : "done",
                    duration: Date.now() - tool.t0,
                  }
                : entry,
            );
          }
          break;
        }
        case "usage": {
          const last = Number(event.last_input || event.input_per_request || 0);
          if (last > 0) setContextTokens(last);
          break;
        }
        case "notice":
          closeAssistant();
          pushSystem(stripInternal(event.text || ""));
          break;
        case "interrupt":
          closeAssistant();
          push({
            id: nextId(),
            kind: "interrupt",
            question: stripInternal(event.question || ""),
            candidates: event.candidates || [],
          });
          break;
        case "done": {
          closeAssistant();
          for (const tool of openTools.current) {
            patch(tool.id, (entry) =>
              entry.kind === "tool" ? { ...entry, status: "done" } : entry,
            );
          }
          openTools.current = [];
          const rawDone = event.text || "";
          const summary = extractSummary(rawDone);
          const isSlash = lastWasSlash.current;
          // slash 命令输出是用户主动请求的正文（/memory 含 [RULES]），不套助手净化。
          const text = isSlash ? rawDone.trim() : cleanAssistant(rawDone).trim();
          if (isSlash) {
            if (text) pushSystem(text);
          } else if (text && !assistantHadText.current) {
            push({
              id: nextId(),
              kind: "assistant",
              text,
              shown: text.length,
              done: true,
              summary,
              raw: rawDone,
            });
          }
          assistantHadText.current = false;
          lastWasSlash.current = false;
          const usage = event.usage || {};
          setContextTokens(
            Number(usage.last_input || usage.input_per_request || usage.input) || 0,
          );
          setUsageTotal((prev) => ({
            requests: prev.requests + (usage.requests || 0),
            input: prev.input + (usage.input || 0),
            output: prev.output + (usage.output || 0),
          }));
          setEntries((prev) =>
            prev.some((entry) => entry.kind === "interrupt" && !entry.answered)
              ? prev.map((entry) =>
                  entry.kind === "interrupt" && !entry.answered
                    ? { ...entry, answered: true }
                    : entry,
                )
              : prev,
          );
          setBusy(false);
          void send({ type: "get_sessions" }).catch(() => undefined);
          break;
        }
        case "exit":
          if (exitedRef.current) break;
          exitedRef.current = true;
          closeAssistant();
          setConnected(false);
          setBusy(false);
          esRef.current?.close();
          pushSystem("后端已退出，请重启 ui/server.mjs");
          break;
      }
    },
    [closeAssistant, nextId, patch, push, pushSystem, resetUi],
  );

  useEffect(() => {
    const es = connect(handleEvent, () => setConnected(false));
    esRef.current = es;
    return () => {
      es.close();
      esRef.current = null;
    };
  }, [handleEvent]);

  const submitUserText = useCallback(
    (text: string) => {
      const pending = entries.findLast(
        (entry) => entry.kind === "interrupt" && !entry.answered,
      );
      if (pending) {
        push({ id: nextId(), kind: "user", text });
        patch(pending.id, (entry) =>
          entry.kind === "interrupt" ? { ...entry, answered: true } : entry,
        );
        void send({ type: "answer", text }).catch(() => undefined);
        return;
      }
      if (text === "/clear") {
        clearChat();
        return;
      }
      if (text === "/theme") {
        onTheme?.();
        return;
      }
      const cmd = text.split(/\s+/)[0].toLowerCase();
      const rest = text.slice(cmd.length).trim();
      if (cmd === "/new") {
        if (busyRef.current) {
          pushSystem("当前任务仍在运行，先中断再开新会话。");
          return;
        }
        push({ id: nextId(), kind: "user", text });
        void send({ type: "new_session" }).catch((err: Error) => {
          pushSystem(`新建会话失败: ${err.message}`);
        });
        return;
      }
      if (cmd === "/model" || cmd === "/mode") {
        if (!rest) {
          push({ id: nextId(), kind: "user", text });
          setModal("model");
          void send({ type: "get_models" }).catch(() => undefined);
          return;
        }
        if (/^\d+$/.test(rest)) {
          push({ id: nextId(), kind: "user", text });
          void send({ type: "set_model", index: Number(rest) - 1 }).catch((err: Error) => {
            pushSystem(`切换模型失败: ${err.message}`);
          });
          return;
        }
      }
      if (cmd === "/workspace") {
        push({ id: nextId(), kind: "user", text });
        if (!rest) {
          setModal("workspace");
          void send({ type: "get_workspace" }).catch(() => undefined);
        } else {
          void send({ type: "set_workspace", path: rest }).catch((err: Error) => {
            pushSystem(`切换工作空间失败: ${err.message}`);
          });
        }
        return;
      }
      if (BLOCKED_COMMANDS.includes(text.split(/\s+/)[0])) {
        pushSystem(
          "Web 端已拦截退出命令：请用顶栏「退出」按钮，或直接关闭页面后停掉 ui/server.mjs。",
        );
        return;
      }
      push({ id: nextId(), kind: "user", text });
      lastWasSlash.current = text.startsWith("/");
      assistantHadText.current = false;
      openAssistant.current = null;
      openTools.current = [];
      setStartedAt(Date.now());
      setBusy(true);
      void send({ type: "task", text }).catch((err: Error) => {
        setBusy(false);
        pushSystem(`发送失败: ${err.message}`);
      });
    },
    [
      clearChat,
      entries,
      nextId,
      onTheme,
      patch,
      push,
      pushSystem,
    ],
  );

  const closeModal = useCallback(() => setModal(null), []);

  const openModels = useCallback(() => {
    setModal("model");
    void send({ type: "get_models" }).catch((err: Error) => {
      pushSystem(`读取模型配置失败: ${err.message}`);
    });
  }, [pushSystem]);

  const openWorkspace = useCallback(() => {
    setModal("workspace");
    void send({ type: "get_workspace" }).catch((err: Error) => {
      pushSystem(`读取工作空间失败: ${err.message}`);
    });
  }, [pushSystem]);

  const saveModelConfig = useCallback(
    (index: number, config: Record<string, string>) => {
      void send({ type: "save_model", index, config }).catch((err: Error) => {
        pushSystem(`保存模型失败: ${err.message}`);
      });
    },
    [pushSystem],
  );

  const revealModels = useCallback(() => {
    void send({ type: "get_models", reveal: true }).catch((err: Error) => {
      pushSystem(`读取模型 Key 失败: ${err.message}`);
    });
  }, [pushSystem]);

  const switchModel = useCallback(
    (index: number) => {
      void send({ type: "set_model", index }).catch((err: Error) => {
        pushSystem(`切换模型失败: ${err.message}`);
      });
    },
    [pushSystem],
  );

  const closeConfirm = useCallback(() => setPendingDelete(null), []);

  const saveWorkspace = useCallback(
    (path: string) => {
      void send({ type: "set_workspace", path }).catch((err: Error) => {
        pushSystem(`切换工作空间失败: ${err.message}`);
      });
      closeModal();
    },
    [closeModal, pushSystem],
  );

  const newSession = useCallback(() => {
    if (busyRef.current) {
      pushSystem("当前任务仍在运行，先中断再开新会话。");
      return;
    }
    void send({ type: "new_session" }).catch((err: Error) => {
      pushSystem(`新建会话失败: ${err.message}`);
    });
  }, [pushSystem]);

  const openSession = useCallback(
    (session: SessionItem) => {
      if (busyRef.current) {
        pushSystem("当前任务仍在运行，先中断再切换会话。");
        return;
      }
      void send({ type: "switch_session", thread_id: session.thread_id }).catch(
        (err: Error) => {
          pushSystem(`切换会话失败: ${err.message}`);
        },
      );
    },
    [pushSystem],
  );

  const requestDeleteSession = useCallback(
    (session: SessionItem) => {
      if (busyRef.current) {
        pushSystem("当前任务仍在运行，先中断再删除会话。");
        return;
      }
      setPendingDelete({ kind: "session", session });
    },
    [pushSystem],
  );

  const requestDeleteWorkspace = useCallback(
    (workspacePath: string) => {
      if (busyRef.current) {
        pushSystem("当前任务仍在运行，先中断再删除工作区。");
        return;
      }
      const count = sessions.filter(
        (item) => (item.workspace || item.workspace_dir || "其他") === workspacePath,
      ).length;
      setPendingDelete({ kind: "workspace", workspace: workspacePath, count });
    },
    [pushSystem, sessions],
  );

  const confirmDelete = useCallback(() => {
    if (!pendingDelete) return;
    setPendingDelete(null);
    if (pendingDelete.kind === "session") {
      void send({ type: "delete_session", thread_id: pendingDelete.session.thread_id })
        .catch((err: Error) => pushSystem(`删除会话失败: ${err.message}`));
    } else {
      void send({ type: "delete_workspace", path: pendingDelete.workspace })
        .catch((err: Error) => pushSystem(`删除工作区失败: ${err.message}`));
    }
  }, [pendingDelete, pushSystem]);

  const confirmMessage = (() => {
    if (!pendingDelete) return "";
    if (pendingDelete.kind === "session") {
      const session = pendingDelete.session;
      const shared =
        (session.workspace || "") && session.workspace === session.workspace_dir;
      return [
        `即将删除会话「${session.title}」。`,
        "",
        "将删除：该会话的对话记录与 LangGraph 检查点。",
        shared
          ? "该会话使用共享工作区根目录，文件不会删除（请用工作区删除来清理目录）。"
          : `该会话独占的目录及其中全部文件会一起删除：\n${session.workspace_dir}`,
        "",
        "此操作不可恢复。",
      ].join("\n");
    }
    return [
      `即将删除工作区：\n${pendingDelete.workspace}`,
      "",
      `将删除：该工作区下 ${pendingDelete.count} 个会话、检查点，以及目录中的全部文件。`,
      "",
      "此操作不可恢复。",
    ].join("\n");
  })();

  const hasPendingQuestion =
    entries.findLast((entry) => entry.kind === "interrupt" && !entry.answered) !== undefined;

  const tokens = usageTotal.input + usageTotal.output;

  return {
    entries,
    busy,
    connected,
    model,
    cwd,
    workspace,
    workspaceRoot,
    defaultWorkspace,
    models,
    activeModel,
    modal,
    pendingDelete,
    confirmMessage,
    sessions,
    workspaces,
    activeThreadId,
    kernelCommands,
    usageTotal,
    tokens,
    contextTokens,
    contextCharCap,
    startedAt,
    hasPendingQuestion,
    submitUserText,
    doAbort,
    clearChat,
    pushSystem,
    closeModal,
    closeConfirm,
    openModels,
    openWorkspace,
    saveModelConfig,
    revealModels,
    switchModel,
    saveWorkspace,
    newSession,
    openSession,
    requestDeleteSession,
    requestDeleteWorkspace,
    confirmDelete,
  };
}

export type AgentSession = ReturnType<typeof useAgentSession>;
