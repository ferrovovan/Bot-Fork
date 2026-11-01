import { Bot } from "lucide-react";
import { ChatSimulator } from "./components/ChatSimulator";
import { HowItWorks } from "./components/HowItWorks";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-sky-400 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20">
              <Bot className="w-6 h-6" />
            </div>
            <div>
              <span className="font-bold text-base tracking-tight text-white">
                СценоМост <span className="text-indigo-400">Bot Fork</span>
              </span>
              <p className="text-xs text-slate-400 hidden sm:block">
                Python-библиотека прототипирования диалоговых сцен (Telegram &amp; ВКонтакте)
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-mono">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-900 border border-slate-800 text-slate-300">
              <span>одна платформа на процесс</span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-900 border border-slate-800 text-indigo-300">
              <span>AGPL-3.0</span>
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-10">
        <ChatSimulator />
        <HowItWorks />
      </main>

      <footer className="border-t border-slate-900 bg-slate-950 py-4 text-center text-xs text-slate-400">
        <p>СценоМост Bot Fork • библиотека диалоговых сцен для Telegram и ВКонтакте • Лицензия AGPL-3.0</p>
      </footer>
    </div>
  );
}
