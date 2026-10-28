import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Contrôle optimiste : sans cookie de session, retour à la connexion.
// La validité réelle est vérifiée par l'API (GET /auth/moi, 401).
export function proxy(request: NextRequest) {
  if (!request.cookies.has("merci_session")) {
    return NextResponse.redirect(new URL("/connexion", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!connexion|api|_next/static|_next/image|assets|icon\\.png|favicon\\.ico).*)"],
};
