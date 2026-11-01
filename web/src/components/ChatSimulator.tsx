import React, { useState, useEffect, useRef } from "react";
import {
  Send,
  RotateCcw,
  Bot,
  Terminal,
  Layers,
  Info
} from "lucide-react";

interface ButtonItem {
  label: string;
  value: string;
}

interface ChatMessage {
  id: string;
  sender: "user" | "bot";
  text: string;
  buttons?: ButtonItem[];
  timestamp: string;
  isError?: boolean;
}

interface SessionData {
  platform: "telegram" | "vk";
  userId: string;
  chatId: string;
  sceneId: string | null;
  stepId: string | null;
  data: Record<string, string>;
}

export const ChatSimulator: React.FC = () => {
  const [platform, setPlatform] = useState<"telegram" | "vk">("telegram");
  const [userId] = useState("1042");
  const [chatId] = useState("1042");
  const [inputText, setInputText] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [session, setSession] = useState<SessionData>({
    platform: "telegram",
    userId: "1042",
    chatId: "1042",
    sceneId: null,
    stepId: null,
    data: {},
  });
  const [lastRawEvent, setLastRawEvent] = useState<any>(null);
  const [lastRawResult, setLastRawResult] = useState<any>(null);
  const [execTimeMs, setExecTimeMs] = useState<number | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Reset or switch platform
  const handlePlatformChange = async (newPlat: "telegram" | "vk") => {
    setPlatform(newPlat);
    setSession({
      platform: newPlat,
      userId,
      chatId,
      sceneId: null,
      stepId: null,
      data: {},
    });
    setMessages([]);
    try {
      await fetch("/api/bot-fork/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform: newPlat, user_id: userId, chat_id: chatId }),
      });
    } catch (e) {
      // ignore
    }
  };

  const handleResetSession = async () => {
    setLoading(true);
    try {
      await fetch("/api/bot-fork/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform, user_id: userId, chat_id: chatId }),
      });
      setMessages([]);
      setSession({
        platform,
        userId,
        chatId,
        sceneId: null,
        stepId: null,
        data: {},
      });
      setLastRawEvent(null);
      setLastRawResult(null);
      setExecTimeMs(null);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const sendMessage = async (textToSend: string | null, payloadToSend: string | null = null) => {
    if (!textToSend && !payloadToSend) return;

    const userDisplayText = textToSend || `[Выбрано: ${payloadToSend}]`;
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      sender: "user",
      text: userDisplayText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText("");
    setLoading(true);

    const eventPayload = {
      platform,
      user_id: userId,
      chat_id: chatId,
      text: textToSend,
      payload: payloadToSend,
    };
    setLastRawEvent(eventPayload);

    const startTime = performance.now();

    try {
      const response = await fetch("/api/bot-fork/event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(eventPayload),
      });

      const elapsed = performance.now() - startTime;
      setExecTimeMs(elapsed);

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`);
      }

      const result = await response.json();
      setLastRawResult(result);

      // Update session state display
      if (result.clear_session) {
        setSession({
          platform,
          userId,
          chatId,
          sceneId: null,
          stepId: null,
          data: {},
        });
      } else if (result.session_after) {
        setSession({
          platform,
          userId,
          chatId,
          sceneId: result.session_after.scene_id,
          stepId: result.session_after.step_id,
          data: result.session_after.data || {},
        });
      }

      // Add bot messages
      if (result.messages && result.messages.length > 0) {
        result.messages.forEach((msg: any, idx: number) => {
          setMessages((prev) => [
            ...prev,
            {
              id: `${Date.now()}_${idx}`,
              sender: "bot",
              text: msg.text,
              buttons: msg.buttons || [],
              timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
              isError: !!result.error,
            },
          ]);
        });
      }
    } catch (err: any) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          sender: "bot",
          text: `Ошибка выполнения ядра: ${err.message}`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          isError: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleQuickCommand = (cmd: string) => {
    sendMessage(cmd, null);
  };

  const handleButtonClick = (button: ButtonItem) => {
    // When button is clicked, we pass its value as payload
    sendMessage(null, button.value);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-125px)] min-h-[640px]">
      {/* Left Column: Chat Device Mockup (7 cols) */}
      <div className="lg:col-span-7 flex flex-col bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
        {/* Simulator Top Control Bar */}
        <div className="flex items-center justify-between px-5 py-3.5 bg-slate-950/80 border-b border-slate-800 backdrop-blur">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Платформа:</span>
            <div className="inline-flex rounded-lg bg-slate-800/80 p-0.5 border border-slate-700/60">
              <button
                onClick={() => handlePlatformChange("telegram")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition ${
                  platform === "telegram"
                    ? "bg-sky-500 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
                Telegram
              </button>
              <button
                onClick={() => handlePlatformChange("vk")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition ${
                  platform === "vk"
                    ? "bg-blue-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
                ВКонтакте
              </button>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {execTimeMs !== null && (
              <span className="text-xs text-emerald-400 font-mono flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                {execTimeMs.toFixed(1)} ms
              </span>
            )}
            <button
              onClick={handleResetSession}
              disabled={loading}
              title="Сбросить сессию"
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 bg-slate-800 hover:bg-slate-700 px-2.5 py-1.5 rounded-md border border-slate-700 transition"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Сброс
            </button>
          </div>
        </div>

        {/* Chat Header (Styled like Telegram or VK) */}
        <div
          className={`px-5 py-3 flex items-center justify-between ${
            platform === "telegram"
              ? "bg-gradient-to-r from-sky-900/60 to-slate-900 border-b border-sky-800/40"
              : "bg-gradient-to-r from-blue-900/60 to-slate-900 border-b border-blue-800/40"
          }`}
        >
          <div className="flex items-center gap-3">
            <div
              className={`w-9 h-9 rounded-full flex items-center justify-center font-bold text-white text-sm shadow ${
                platform === "telegram" ? "bg-sky-500" : "bg-blue-600"
              }`}
            >
              {platform === "telegram" ? "TG" : "VK"}
            </div>
            <div>
              <div className="text-sm font-semibold text-slate-100 flex items-center gap-1.5">
                {platform === "telegram" ? "Bot Fork Demo (Telegram)" : "СценоМост Бот (ВКонтакте)"}
              </div>
              <div className="text-xs text-emerald-400 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                бот активен (one platform/process)
              </div>
            </div>
          </div>

          <div className="text-right">
            <span className="text-[11px] text-slate-400">Пользователь: ID #{userId}</span>
          </div>
        </div>

        {/* Chat Messages Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-950/60 scrollbar-thin">
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-400 space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                <Bot className="w-6 h-6" />
              </div>
              <div className="max-w-xs space-y-1">
                <p className="text-sm font-medium text-slate-200">Чат пуст. Начните сценарий</p>
                <p className="text-xs text-slate-400">
                  Отправьте команду <code className="text-indigo-300 font-mono bg-slate-800 px-1 py-0.5 rounded">/info</code>, чтобы запустить анкету из 3 шагов.
                </p>
              </div>

              <div className="flex flex-wrap gap-2 justify-center pt-2">
                <button
                  onClick={() => handleQuickCommand("/info")}
                  className="px-3 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/30 text-indigo-300 text-xs font-medium transition"
                >
                  🚀 Запустить /info
                </button>
                <button
                  onClick={() => handleQuickCommand("Привет!")}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition"
                >
                  Тест без сессии
                </button>
              </div>
            </div>
          )}

          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex flex-col ${m.sender === "user" ? "items-end" : "items-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2.5 shadow-sm text-sm ${
                  m.sender === "user"
                    ? platform === "telegram"
                      ? "bg-sky-600 text-white rounded-br-none"
                      : "bg-blue-600 text-white rounded-br-none"
                    : m.isError
                    ? "bg-rose-950/80 border border-rose-800/80 text-rose-200 rounded-bl-none"
                    : "bg-slate-800/95 border border-slate-700/80 text-slate-100 rounded-bl-none"
                }`}
              >
                <div className="whitespace-pre-wrap leading-relaxed">{m.text}</div>
                <div className="text-[10px] opacity-60 text-right mt-1">{m.timestamp}</div>
              </div>

              {/* Bot Inline Buttons */}
              {m.buttons && m.buttons.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5 max-w-[85%]">
                  {m.buttons.map((btn, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleButtonClick(btn)}
                      disabled={loading}
                      className={`px-3.5 py-1.5 rounded-xl text-xs font-medium transition shadow-sm flex items-center gap-1.5 ${
                        platform === "telegram"
                          ? "bg-sky-900/40 hover:bg-sky-800/60 border border-sky-600/40 text-sky-200 hover:text-white"
                          : "bg-blue-900/40 hover:bg-blue-800/60 border border-blue-600/40 text-blue-200 hover:text-white"
                      }`}
                    >
                      <span>{btn.label}</span>
                      <span className="text-[10px] opacity-40 font-mono">({btn.value})</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex items-center gap-2 text-xs text-slate-400 bg-slate-900/80 px-3 py-1.5 rounded-full w-max border border-slate-800">
              <div className="w-2 h-2 rounded-full bg-indigo-400 animate-ping" />
              Ядро обрабатывает событие...
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick Action Chips */}
        <div className="px-4 py-2 bg-slate-950/90 border-t border-slate-800/80 flex items-center gap-2 overflow-x-auto text-xs scrollbar-none">
          <span className="text-slate-400 whitespace-nowrap text-[11px] font-medium">Быстрые команды:</span>
          <button
            onClick={() => handleQuickCommand("/info")}
            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 whitespace-nowrap transition"
          >
            /info (Старт)
          </button>
          <button
            onClick={() => handleQuickCommand("/cancel")}
            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 whitespace-nowrap transition"
          >
            /cancel (Отмена)
          </button>
          <button
            onClick={() => handleQuickCommand("   ")}
            className="px-2.5 py-1 rounded bg-slate-800/80 hover:bg-slate-700 text-amber-300 whitespace-nowrap transition"
          >
            Пустой ввод (ошибка)
          </button>
          <button
            onClick={() => handleQuickCommand("/help")}
            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 whitespace-nowrap transition"
          >
            /help (неизвестная)
          </button>
        </div>

        {/* Input Bar */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage(inputText);
          }}
          className="p-3 bg-slate-950 border-t border-slate-800 flex items-center gap-2"
        >
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Введите ответ или команду (/info, /cancel)..."
            disabled={loading}
            className="flex-1 bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
          />
          <button
            type="submit"
            disabled={loading || !inputText.trim()}
            className="p-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 text-white transition flex items-center justify-center shadow"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>

      {/* Right Column: Live FSM State & Protocol Inspector (5 cols) */}
      <div className="lg:col-span-5 flex flex-col gap-4 overflow-y-auto pr-1">
        {/* Active Session Card */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-indigo-400">
              <Layers className="w-4 h-4" />
              <span>Состояние FSM (MemoryStateStorage)</span>
            </div>
            <span
              className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${
                session.sceneId
                  ? "bg-emerald-950 border border-emerald-800 text-emerald-400"
                  : "bg-slate-800 text-slate-400"
              }`}
            >
              {session.sceneId ? "АКТИВНАЯ СЕССИЯ" : "НЕТ СЕССИИ"}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80">
              <span className="text-slate-400 block text-[10px] uppercase">SessionKey.platform</span>
              <span className="font-mono text-slate-200 font-medium">{session.platform}</span>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80">
              <span className="text-slate-400 block text-[10px] uppercase">user_id / chat_id</span>
              <span className="font-mono text-slate-200 font-medium">{session.userId}</span>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80">
              <span className="text-slate-400 block text-[10px] uppercase">scene_id</span>
              <span className="font-mono text-amber-300 font-medium">{session.sceneId || "None"}</span>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80">
              <span className="text-slate-400 block text-[10px] uppercase">step_id</span>
              <span className="font-mono text-sky-300 font-medium">{session.stepId || "None"}</span>
            </div>
          </div>

          {/* Accumulated survey data */}
          <div className="space-y-1.5 pt-1">
            <span className="text-[11px] font-medium text-slate-400">
              Накопленные ответы анкеты (session.data):
            </span>
            <div className="bg-slate-950 rounded-lg p-2.5 border border-slate-800 font-mono text-xs text-slate-300 min-h-[52px]">
              {Object.keys(session.data).length === 0 ? (
                <span className="text-slate-400 italic">Данные пока пусты (нет принятых шагов)</span>
              ) : (
                <div className="space-y-1">
                  {Object.entries(session.data).map(([k, v]) => (
                    <div key={k} className="flex justify-between items-center text-xs">
                      <span className="text-indigo-400 font-medium">{k}:</span>
                      <span className="text-slate-100 bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800">
                        {v}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Raw Protocol Events Inspector */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow space-y-3 flex-1">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-300">
              <Terminal className="w-4 h-4 text-emerald-400" />
              <span>Протокол взаимодействия (Контракты)</span>
            </div>
            <span className="text-[11px] text-slate-400">JSON</span>
          </div>

          {/* IncomingEvent */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-medium text-slate-300 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-sky-400" />
                Входящее IncomingEvent
              </span>
              <span className="text-slate-400 text-[10px] font-mono">
                Update -&gt; normalize_event()
              </span>
            </div>
            <pre className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 text-[11px] font-mono text-sky-300 overflow-x-auto max-h-[140px] leading-tight">
              {lastRawEvent ? JSON.stringify(lastRawEvent, null, 2) : "// Ожидание входящего события..."}
            </pre>
          </div>

          {/* HandlerResult */}
          <div className="space-y-1 pt-1">
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-medium text-slate-300 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                Исходящий HandlerResult ядра
              </span>
              <span className="text-slate-400 text-[10px] font-mono">
                FSMEngine -&gt; format_outgoing()
              </span>
            </div>
            <pre className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 text-[11px] font-mono text-emerald-300 overflow-x-auto max-h-[170px] leading-tight">
              {lastRawResult ? JSON.stringify(lastRawResult, null, 2) : "// Ожидание ответа ядра..."}
            </pre>
          </div>

          {/* Branding Note */}
          <div className="p-2.5 rounded-lg bg-indigo-950/40 border border-indigo-900/60 text-[11px] text-indigo-300 flex items-start gap-2">
            <Info className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
            <div>
              <strong>Бесплатный режим MVP:</strong> подпись{" "}
              <code className="bg-indigo-900/60 px-1 rounded text-indigo-200">
                Made with Bot Fork
              </code>{" "}
              добавляется ядром к каждому исходящему видимому тексту ровно один раз.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
