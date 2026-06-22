import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SESSION_COOKIE, isAuthed } from "@/lib/auth";

// Next.js 16: this file replaces the old `middleware.ts`. Gate every page
// behind the password cookie; redirect to /login otherwise.
export async function proxy(req: NextRequest) {
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  if (await isAuthed(token)) return NextResponse.next();

  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = {
  // run on everything except the login page, Next internals, and static assets
  matcher: ["/((?!login|_next/static|_next/image|favicon.ico).*)"],
};
