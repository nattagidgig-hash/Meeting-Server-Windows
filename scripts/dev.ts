#!/usr/bin/env bun
/**
 * `bun run dev`
 *
 * Dev-only runner: serves web/ with no-cache + live reload and proxies /api to
 * the local FastAPI process, so editing CSS/JS/HTML updates the browser instantly.
 * Production on the Windows server still uses run.py (see Start-Server.cmd).
 *
 * Env:
 *   MEETING_PORT   API port (default 8765, same as app config)
 *   DEV_PORT       dev server port (default 5173)
 *   MEETING_PYTHON python executable to use (default .venv, then python3)
 *   MEETING_DATA   data directory passed through to the API
 */
import { existsSync, watch } from "node:fs";
import { extname, join, resolve } from "node:path";

const ROOT = resolve(import.meta.dir, "..");
const WEB = join(ROOT, "web");
const API_PORT = Number(process.env.MEETING_PORT || 8765);
const DEV_PORT = Number(process.env.DEV_PORT || 5173);
const WEB_ONLY = process.argv.includes("--web-only");
const API = `http://127.0.0.1:${API_PORT}`;

function pythonPath(): string {
  if (process.env.MEETING_PYTHON) return process.env.MEETING_PYTHON;
  const venv = process.platform === "win32"
    ? join(ROOT, ".venv", "Scripts", "python.exe")
    : join(ROOT, ".venv", "bin", "python");
  if (existsSync(venv)) return venv;
  return process.platform === "win32" ? "python" : "python3";
}

let api: ReturnType<typeof Bun.spawn> | null = null;
if (!WEB_ONLY) {
  const py = pythonPath();
  console.log(`[dev] api    ${py} -m uvicorn app.server:app --port ${API_PORT}`);
  api = Bun.spawn({
    cmd: [py, "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", String(API_PORT), "--log-level", "warning"],
    cwd: ROOT,
    env: { ...process.env, PYTHONPATH: ROOT },
    stdout: "inherit",
    stderr: "inherit",
  });
}

/* ---------- live reload over SSE ---------- */
const clients = new Set<ReadableStreamDefaultController<Uint8Array>>();
const encoder = new TextEncoder();
function broadcast() {
  const payload = encoder.encode("data: reload\n\n");
  for (const controller of clients) {
    try { controller.enqueue(payload); } catch { clients.delete(controller); }
  }
}
try { watch(WEB, { recursive: true }, () => broadcast()); } catch (err) { console.warn("[dev] watch unavailable:", err); }
setInterval(() => {
  for (const controller of clients) { try { controller.enqueue(encoder.encode(": ping\n\n")); } catch { clients.delete(controller); } }
}, 25000);

const RELOAD = `<script>(()=>{try{const s=new EventSource("/__live");s.onmessage=()=>location.reload();}catch(e){}})();</script>`;

const MIME: Record<string, string> = {
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
};

const server = Bun.serve({
  port: DEV_PORT,
  idleTimeout: 60,
  async fetch(req) {
    const url = new URL(req.url);
    const path = decodeURIComponent(url.pathname);

    if (path === "/__live") {
      let ref: ReadableStreamDefaultController<Uint8Array> | null = null;
      const stream = new ReadableStream<Uint8Array>({
        start(controller) { ref = controller; clients.add(controller); controller.enqueue(encoder.encode("retry: 1500\n\n")); },
        cancel() { if (ref) clients.delete(ref); },
      });
      return new Response(stream, {
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" },
      });
    }

    if (path.startsWith("/api/") || path === "/health") {
      const headers = new Headers(req.headers);
      headers.delete("host");
      const init: RequestInit = { method: req.method, headers, redirect: "manual" };
      if (req.method !== "GET" && req.method !== "HEAD") {
        init.body = req.body;
        (init as RequestInit & { duplex: string }).duplex = "half";
      }
      try { return await fetch(`${API}${path}${url.search}`, init); }
      catch {
        return Response.json({ detail: "API ยังไม่พร้อม (กำลังเริ่มเซิร์ฟเวอร์) กรุณาลองอีกครั้ง" }, { status: 503 });
      }
    }

    if (path === "/" || path === "/index.html") {
      const html = (await Bun.file(join(WEB, "index.html")).text()).replace("</body>", `${RELOAD}</body>`);
      return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
    }

    const clean = path.replace(/\.\./g, "");
    const file = Bun.file(join(WEB, clean));
    if (await file.exists()) {
      return new Response(file, {
        headers: { "Content-Type": MIME[extname(clean)] || file.type || "application/octet-stream", "Cache-Control": "no-store" },
      });
    }
    return new Response("Not found", { status: 404, headers: { "Content-Type": "text/plain; charset=utf-8" } });
  },
});

console.log(`[dev] web    http://localhost:${server.port}   (live reload on web/ changes)`);
if (!WEB_ONLY) console.log(`[dev] api    ${API}`);

function shutdown() { try { api?.kill(); } catch {} process.exit(0); }
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
