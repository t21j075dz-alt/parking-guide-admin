import { createClient } from "npm:@supabase/supabase-js@2.57.0";

const BASE_URL = Deno.env.get("SUPABASE_URL") || "";
const ANON = Deno.env.get("SUPABASE_ANON_KEY") || "";
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const admin = createClient(BASE_URL, SERVICE, { auth: { persistSession: false, autoRefreshToken: false } });
const originList = [
  "https://t21j075dz-alt.github.io",
];

function headers(req: Request) {
  const origin = req.headers.get("origin") || "";
  return {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": originList.includes(origin) ? origin : "https://t21j075dz-alt.github.io",
    "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-parking-voice-worker",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
    "Cache-Control": "no-store",
  };
}
function response(req: Request, data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: headers(req) });
}
async function adminUser(req: Request) {
  const bearer = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
  if (!bearer) return false;
  const client = createClient(BASE_URL, ANON, { auth: { persistSession: false, autoRefreshToken: false } });
  const { data, error } = await client.auth.getUser(bearer);
  if (error || !data?.user?.id) return false;
  const { data: person } = await admin.from("parking_camera_operators")
    .select("user_id").eq("user_id", data.user.id).maybeSingle();
  return Boolean(person);
}
async function sha256(text: string) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(bytes)].map(b => b.toString(16).padStart(2, "0")).join("");
}
const safeText = (x: unknown) => typeof x === "string" && x.trim().length > 0 && x.length <= 160;
async function enqueue(items: unknown[]) {
  if (!items?.length || items.length > 250) return { error: "1〜250件で送信してください" };
  const seen = new Set<string>();
  const records = [];
  for (const item of items) {
    if (!item || typeof item !== "object") return { error: "invalid item" };
    const { text, type } = item as {text?:unknown,type?:unknown};
    if (!safeText(text) || !["facility","tenant","other"].includes(String(type))) return { error: "invalid name" };
    const message = (text as string).trim();
    if (seen.has(message)) continue;
    seen.add(message);
    const hash = await sha256("voice-cache-v1:8:" + message);
    records.push({
      audio_hash: hash, spoken_text: message, source_type: String(type),
      status: "pending", locale: "ja-JP", voice_id: 8,
    });
  }
  const { error } = await admin.from("parking_voice_jobs").upsert(records, {
    onConflict: "audio_hash", ignoreDuplicates: true,
  });
  if (error) return { error: "queue insert failed" };
  return { accepted: records.length };
}
function validAudioUrl(raw: unknown) {
  if (typeof raw !== "string") throw new Error("audio-url-invalid");
  const u = new URL(raw);
  if (u.protocol !== "https:" || !/^audio\d+\.tts\.quest$/.test(u.hostname) ||
    !/^\/v1\/data\/[a-zA-Z0-9]+\/(?:audio\.(?:wav|mp3)|status\.json)$/.test(u.pathname)) throw new Error("audio-url-invalid");
  return u.href;
}
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
async function synthesize(text: string) {
  const url = "https://api.tts.quest/v3/voicevox/synthesis?speaker=8&text=" + encodeURIComponent(text);
  const result = await fetch(url, { signal: AbortSignal.timeout(12000) });
  if (result.status === 429) throw new Error("tts-rate-limited");
  if (!result.ok) throw new Error("tts-response-" + result.status);
  const payload = await result.json();
  if (!payload.success) throw new Error("tts-no-result");
  const statusUrl = validAudioUrl(payload.audioStatusUrl);
  const downloadUrl = validAudioUrl(payload.mp3DownloadUrl);
  for (let retry = 0; retry < 28; retry++) {
    const response = await fetch(statusUrl, { signal: AbortSignal.timeout(12000) });
    if (response.status === 429) throw new Error("tts-rate-limited");
    if (!response.ok) throw new Error("tts-status-" + response.status);
    const st = await response.json();
    if (st.isAudioError) throw new Error("tts-generation-failed");
    if (st.isAudioReady) {
      const audio = await fetch(downloadUrl, { signal: AbortSignal.timeout(18000) });
      if (audio.status === 429) throw new Error("tts-rate-limited");
      if (!audio.ok) throw new Error("tts-download-" + audio.status);
      const b = await audio.arrayBuffer();
      if (b.byteLength < 200 || b.byteLength > 2097152) throw new Error("tts-file-size");
      return b;
    }
    await sleep(800);
  }
  throw new Error("tts-timeout");
}
async function work() {
  const { data: cooldown } = await admin.from("parking_voice_worker_config")
    .select("secret_value").eq("key", "cooldown_until").maybeSingle();
  const blockedUntil = Date.parse(cooldown?.secret_value || "");
  if (Number.isFinite(blockedUntil) && blockedUntil > Date.now()) return { status: "cooldown" };
  const { data: claimed, error: claimError } = await admin.rpc("parking_voice_claim_job");
  if (claimError) return { status: "claim-failed" };
  const item = claimed?.[0];
  if (!item) return { status: "empty" };
  try {
    const buffer = await synthesize(item.spoken_text);
    const file = "ja-JP/" + item.audio_hash + ".mp3";
    const { error: uploadError } = await admin.storage.from("parking-voice").upload(file, buffer, {
      contentType: "audio/mpeg", upsert: true,
      cacheControl: "31536000",
    });
    if (uploadError) throw new Error("storage-upload-failed");
    const { error: savedError } = await admin.from("parking_voice_jobs").update({
      status: "ready", storage_path: file, last_error: null,
      updated_at: new Date().toISOString(),
    }).eq("audio_hash", item.audio_hash);
    if (savedError) throw new Error("database-save-failed");
    return { status: "ready" };
  } catch (error) {
    const code = String(error instanceof Error ? error.message : error).slice(0,120);
    const rateLimited = code.includes("rate-limited");
    const seconds = rateLimited ? 30 * 60 : Math.min(3600, 60 * 2 ** Math.min(6,item.attempts));
    if (rateLimited) await admin.from("parking_voice_worker_config").upsert({
      key: "cooldown_until", secret_value: new Date(Date.now() + seconds * 1000).toISOString(),
    });
    await admin.from("parking_voice_jobs").update({
      status: item.attempts >= 8 ? "failed" : "retry",
      next_attempt_at: new Date(Date.now() + seconds * 1000).toISOString(),
      last_error: code, updated_at: new Date().toISOString(),
    }).eq("audio_hash", item.audio_hash);
    return { status: "retry", reason: code };
  }
}
async function checkWorkerToken(req: Request) {
  const token = req.headers.get("x-parking-voice-worker") || "";
  if (token.length < 32) return false;
  const { data } = await admin.from("parking_voice_worker_config")
    .select("secret_value").eq("key", "worker_token").maybeSingle();
  // 定数時間相当の比較
  const reference = data?.secret_value || "";
  if (token.length !== reference.length) return false;
  let diff = 0;
  for (let i = 0; i < token.length; i++) diff |= token.charCodeAt(i) ^ reference.charCodeAt(i);
  return diff === 0;
}
Deno.serve(async req => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: headers(req) });
  if (req.method !== "POST") return response(req, { error: "POST only" }, 405);
  if (!SERVICE || !BASE_URL || !ANON) return response(req, { error: "service config missing" }, 503);
  let body: Record<string,unknown> = {};
  try { body = await req.json(); } catch { return response(req, { error: "invalid JSON" }, 400); }
  if (body.action === "work") {
    if (!await checkWorkerToken(req)) return response(req, { error: "not authorized" }, 403);
    return response(req, await work());
  }
  if (!await adminUser(req)) return response(req, { error: "administrator authorization required" }, 403);
  if (body.action === "enqueue") {
    const result = await enqueue(body.items as unknown[]);
    if ("error" in result) return response(req, result, 400);
    // 自動生成は30秒間隔のCronで実行し、管理画面の一括登録から
    // 同時に多数のTTS生成要求を出さない。
    return response(req, result);
  }
  if (body.action === "status") {
    // PostgRESTの行数上限で1000件を超える場合も正確に集計。
    const totals = { ready: 0, pending: 0, processing: 0, retry: 0, failed: 0 };
    const byType: Record<string,{ready:number,total:number}> = {
      facility:{ready:0,total:0}, tenant:{ready:0,total:0}, other:{ready:0,total:0}
    };
    let total = 0;
    for (let offset = 0; offset < 100000; offset += 500) {
      const { data, error } = await admin.from("parking_voice_jobs")
        .select("status,source_type").order("audio_hash").range(offset,offset+499);
      if (error) return response(req, { error: "status unavailable" }, 503);
      for (const row of data || []) {
        if (row.status in totals) totals[row.status as keyof typeof totals]++;
        if (row.source_type in byType) {
          byType[row.source_type].total++;
          if (row.status === "ready") byType[row.source_type].ready++;
        }
      }
      total += (data || []).length;
      if (!data || data.length < 500) break;
    }
    const { data: cooldown } = await admin.from("parking_voice_worker_config")
      .select("secret_value").eq("key","cooldown_until").maybeSingle();
    const blockedUntil = Date.parse(cooldown?.secret_value || "");
    return response(req, { totals, byType, total,
      cooldownMinutes: Number.isFinite(blockedUntil) ?
        Math.max(0,Math.ceil((blockedUntil - Date.now()) / 60000)) : 0 });
  }
  if (body.action === "retry-failed") {
    // 生成成功済みMP3は削除・再生成しない。
    // 管理者が明示的に押した場合のみ失敗8回の項目を再試行対象に戻す。
    const { data, error } = await admin.from("parking_voice_jobs")
      .update({ status:"pending", attempts:0, last_error:null,
        next_attempt_at:new Date().toISOString(), updated_at:new Date().toISOString() })
      .eq("status","failed").select("audio_hash");
    if (error) return response(req,{error:"Could not retry failed voice clips"},503);
    return response(req,{requeued:(data || []).length});
  }
  return response(req, { error: "unknown action" }, 400);
});
