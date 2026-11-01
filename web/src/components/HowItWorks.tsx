import React, { useState } from "react";
import {
  Cpu,
  Globe,
  Workflow,
  Zap,
  Database,
  ShieldCheck,
  Check,
} from "lucide-react";

const flowSteps = [
  {
    num: 1,
    title: "Событие мессенджера",
    desc: "Пользователь отправляет команду, текст или нажимает кнопку в Telegram либо ВКонтакте.",
    tag: "Telegram / VK Update",
  },
  {
    num: 2,
    title: "Платформенный адаптер",
    desc: "TelegramAdapter или VKAdapter нормализует событие, извлекая user_id, chat_id, text или payload кнопки в IncomingEvent.",
    tag: "normalize_event()",
  },
  {
    num: 3,
    title: "Маршрутизация (DialogRouter)",
    desc: "Проверяет /cancel до прикладного кода, запрашивает UserSession из StateStorage. Если сессии нет — ищет команду в SceneRegistry.",
    tag: "DialogRouter.route()",
  },
  {
    num: 4,
    title: "Конечный автомат (FSMEngine)",
    desc: "Валидирует ввод текущего шага, сохраняет ответ в session.data, вычисляет переход next_step_id или завершение сцены.",
    tag: "FSMEngine.process_step()",
  },
  {
    num: 5,
    title: "Фирменная подпись (Branding)",
    desc: "К каждому исходящему сообщению ровно один раз добавляется суффикс «Made with Bot Fork», проверяется лимит 4096 символов.",
    tag: "apply_branding()",
  },
  {
    num: 6,
    title: "Отправка и фиксация состояния",
    desc: "Адаптер преобразует текст и кнопки в платформенное API. Только после успеха MemoryStateStorage фиксирует новый шаг либо удаляет сессию.",
    tag: "StateStorage.set() / clear()",
  },
];

const components = [
  {
    name: "BotForkApp",
    icon: Cpu,
    color: "text-indigo-400",
    desc: "Точка входа. Проверяет правило одного адаптера (ENABLED_PLATFORMS=telegram|vk), регистрирует сцены, связывает зависимости и запускает цикл polling.",
  },
  {
    name: "TelegramAdapter",
    icon: Globe,
    color: "text-sky-400",
    desc: "Преобразует Telegram Update и CallbackQuery в IncomingEvent. Формирует OutgoingMessage в виде inline-клавиатуры с callback_data.",
  },
  {
    name: "VKAdapter",
    icon: Globe,
    color: "text-blue-400",
    desc: "Преобразует события ВКонтакте (MessageNew, payload кнопки) в IncomingEvent. Формирует OutgoingMessage в виде inline-клавиатуры.",
  },
  {
    name: "DialogRouter",
    icon: Workflow,
    color: "text-violet-400",
    desc: "Выбор сцены по стартовой команде (/info) или направление события в активный шаг. Обработка системного сброса /cancel.",
  },
  {
    name: "FSMEngine",
    icon: Zap,
    color: "text-purple-400",
    desc: "Проверка входных данных валидаторами шага, сохранение в session.data, вычисление ветвления переходов и формирование итогового отчёта.",
  },
  {
    name: "MemoryStateStorage",
    icon: Database,
    color: "text-emerald-400",
    desc: "Изоляция сессий в памяти процесса по составному SessionKey (platform, user_id, chat_id). Независимые состояния сотен пользователей.",
  },
];

export const HowItWorks: React.FC = () => {
  const [activeStep, setActiveStep] = useState<number>(1);

  return (
    <div className="space-y-6 pb-10">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-5">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div>
            <h3 className="text-lg font-semibold text-white">
              Как устроен один сценарий
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Ветвления, вопросы, кнопки и валидаторы описываются один раз на чистом Python — без платформенных зависимостей.
            </p>
          </div>
          <span className="text-xs font-mono bg-slate-800 text-slate-300 px-2.5 py-1 rounded-md border border-slate-700 whitespace-nowrap">
            Шаг {activeStep} из {flowSteps.length}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {flowSteps.map((s) => (
            <button
              key={s.num}
              onClick={() => setActiveStep(s.num)}
              className={`p-3 rounded-xl border text-left transition flex flex-col justify-between ${
                activeStep === s.num
                  ? "bg-indigo-600/10 border-indigo-500 text-white shadow-md shadow-indigo-500/10"
                  : "bg-slate-950/60 border-slate-800/80 text-slate-400 hover:border-slate-700 hover:text-slate-200"
              }`}
            >
              <span
                className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold mb-2 ${
                  activeStep === s.num ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-400"
                }`}
              >
                {s.num}
              </span>
              <span className="text-xs font-medium line-clamp-2">{s.title}</span>
            </button>
          ))}
        </div>

        <div className="bg-slate-950 rounded-xl p-5 border border-indigo-500/30 flex flex-col sm:flex-row gap-5 items-start sm:items-center">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold text-lg shrink-0 shadow-lg">
            {activeStep}
          </div>
          <div className="flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="text-base font-semibold text-white">{flowSteps[activeStep - 1].title}</h4>
              <span className="text-xs font-mono bg-slate-900 border border-slate-800 text-indigo-300 px-2 py-0.5 rounded">
                {flowSteps[activeStep - 1].tag}
              </span>
            </div>
            <p className="text-sm text-slate-300 leading-relaxed">{flowSteps[activeStep - 1].desc}</p>
          </div>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
        <h3 className="text-lg font-semibold text-white border-b border-slate-800 pb-3">
          Состав ядра и адаптеров
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {components.map((c) => (
            <div key={c.name} className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2">
              <div className={`flex items-center gap-2 ${c.color} font-medium text-sm`}>
                <c.icon className="w-4 h-4" />
                <span className="font-mono">{c.name}</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">{c.desc}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-amber-300">
          <ShieldCheck className="w-4 h-4" />
          <span>Ограничения бесплатной версии</span>
        </div>
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 text-xs text-slate-300 leading-relaxed">
          <li className="flex items-start gap-2">
            <Check className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
            <span>
              <strong>Один адаптер на процесс:</strong> при ENABLED_PLATFORMS=telegram,vk поднимается ConfigError до запуска.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <Check className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
            <span>
              <strong>Фиксированная подпись:</strong> «Made with Bot Fork» добавляется ко всем видимым ответам, параметра отключения в API нет.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <Check className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
            <span>
              <strong>Хранилище в памяти:</strong> внешние СУБД не требуются, перезапуск процесса очищает состояния.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <Check className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
            <span>
              <strong>Лимиты сообщения:</strong> до 4 кнопок (label ≤ 40, value ≤ 64 символов) и 4096 символов текста.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <Check className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
            <span>
              <strong>Чистое ядро:</strong> пакет bot_fork не импортирует aiogram и vkbottle — только адаптеры.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <Check className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
            <span>
              <strong>Безопасный ввод:</strong> ошибки INVALID_INPUT не повреждают текущий шаг и сохранённые данные.
            </span>
          </li>
        </ul>
      </div>
    </div>
  );
};
