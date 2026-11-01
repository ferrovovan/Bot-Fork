import express from "express";
import { createServer as createViteServer } from "vite";
import { execFile } from "child_process";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
// Python core (bot_fork/, examples/, scripts/) lives one level above web/
const REPO_ROOT = path.resolve(__dirname, "..");
const HANDLER = path.join(REPO_ROOT, "scripts", "handle_event.py");
const PYTHON = process.env.PYTHON || "python3";

const SAFE_ID = /^[A-Za-z0-9_-]{1,64}$/;
const PLATFORMS = ["telegram", "vk"];

type SessionBody = {
  platform: string;
  user_id: string;
  chat_id: string;
};

function parseSession(body: any): SessionBody | string {
  const platform = String(body?.platform ?? "telegram").toLowerCase();
  const user_id = String(body?.user_id ?? "1001");
  const chat_id = String(body?.chat_id ?? "1001");
  if (!PLATFORMS.includes(platform)) return `platform must be one of ${PLATFORMS.join(", ")}`;
  if (!SAFE_ID.test(user_id) || !SAFE_ID.test(chat_id)) return "user_id and chat_id must match ^[A-Za-z0-9_-]{1,64}$";
  return { platform, user_id, chat_id };
}

function runHandler(args: string[], stdin: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = execFile(
      PYTHON,
      [HANDLER, ...args],
      {
        cwd: REPO_ROOT,
        env: { ...process.env, PYTHONPATH: REPO_ROOT },
        maxBuffer: 4 * 1024 * 1024,
      },
      (error, stdout, stderr) => {
        if (error) return reject(new Error(stderr || error.message));
        resolve(stdout);
      }
    );
    child.stdin?.write(stdin);
    child.stdin?.end();
  });
}

async function startServer() {
  const app = express();
  const PORT = Number(process.env.PORT) || 3000;

  app.use(express.json());

  app.get("/api/health", (_req, res) => {
    res.json({ ok: true });
  });

  // Execute one event through the Bot Fork Python core
  app.post("/api/bot-fork/event", async (req, res) => {
    const session = parseSession(req.body);
    if (typeof session === "string") return res.status(400).json({ error: session });

    const { platform, user_id, chat_id } = session;
    const payload = {
      platform,
      user_id,
      chat_id,
      text: req.body?.text ?? null,
      payload: req.body?.payload ?? null,
    };

    try {
      const stdout = await runHandler([], JSON.stringify(payload));
      res.json(JSON.parse(stdout.trim()));
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Drop the stored session of a user
  app.post("/api/bot-fork/reset", async (req, res) => {
    const session = parseSession(req.body);
    if (typeof session === "string") return res.status(400).json({ error: session });

    try {
      const stdout = await runHandler(["--reset"], JSON.stringify(session));
      res.json(JSON.parse(stdout.trim()));
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });

  // Development: mount Vite middlewares
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      root: __dirname,
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    // Production: serve the built static bundle
    app.use(express.static(path.join(__dirname, "dist")));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(__dirname, "dist", "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server listening on http://0.0.0.0:${PORT}`);
  });
}

startServer();
