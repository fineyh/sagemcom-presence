"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { SESSION_COOKIE, sessionToken, isAuthed, dashboardPassword } from "@/lib/auth";
import { supabaseAdmin } from "@/lib/supabase";

async function requireAuth() {
  const store = await cookies();
  if (!(await isAuthed(store.get(SESSION_COOKIE)?.value))) {
    throw new Error("Unauthorized");
  }
}

export async function login(formData: FormData) {
  const pw = String(formData.get("password") ?? "").trim();
  const expected = dashboardPassword();
  if (!expected || pw !== expected) {
    redirect("/login?error=1");
  }
  const store = await cookies();
  store.set(SESSION_COOKIE, await sessionToken(), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  redirect("/");
}

export async function logout() {
  const store = await cookies();
  store.delete(SESSION_COOKIE);
  redirect("/login");
}

export async function renameDevice(formData: FormData) {
  await requireAuth();
  const mac = String(formData.get("mac"));
  const name = String(formData.get("custom_name") ?? "").trim();
  await supabaseAdmin()
    .from("devices")
    .update({ custom_name: name || null, updated_at: new Date().toISOString() })
    .eq("mac", mac);
  revalidatePath("/");
  revalidatePath(`/device/${encodeURIComponent(mac)}`);
}

export async function saveNotes(formData: FormData) {
  await requireAuth();
  const mac = String(formData.get("mac"));
  const notes = String(formData.get("notes") ?? "").trim();
  await supabaseAdmin()
    .from("devices")
    .update({ notes: notes || null, updated_at: new Date().toISOString() })
    .eq("mac", mac);
  revalidatePath(`/device/${encodeURIComponent(mac)}`);
}

export async function setHidden(formData: FormData) {
  await requireAuth();
  const mac = String(formData.get("mac"));
  const hidden = String(formData.get("hidden")) === "true";
  await supabaseAdmin()
    .from("devices")
    .update({ hidden, updated_at: new Date().toISOString() })
    .eq("mac", mac);
  revalidatePath("/");
  revalidatePath(`/device/${encodeURIComponent(mac)}`);
}
