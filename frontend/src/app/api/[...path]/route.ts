export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HOP_BY_HOP_HEADERS = [
  "connection",
  "content-length",
  "content-encoding",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
];

function backendUrl(request: Request) {
  const backendOrigin =
    process.env.NEXUS_BACKEND_URL ??
    process.env.NEXT_PUBLIC_NEXUS_BACKEND_URL ??
    "http://127.0.0.1:8000";

  const incoming = new URL(request.url);
  const backendPath = incoming.pathname.replace(/^\/api/, "") || "/";

  return new URL(`${backendPath}${incoming.search}`, backendOrigin);
}

async function proxyRequest(request: Request) {
  const target = backendUrl(request);
  const headers = new Headers(request.headers);

  headers.delete("host");
  headers.delete("connection");

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
    redirect: "manual",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  try {
    const response = await fetch(target, init);
    const responseHeaders = new Headers(response.headers);

    for (const header of HOP_BY_HOP_HEADERS) {
      responseHeaders.delete(header);
    }

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    return Response.json(
      {
        error: "Backend unavailable",
        detail: error instanceof Error ? error.message : "Unknown proxy error",
      },
      { status: 502 }
    );
  }
}

export const GET = proxyRequest;
export const HEAD = proxyRequest;
export const POST = proxyRequest;
export const PATCH = proxyRequest;
export const PUT = proxyRequest;
export const DELETE = proxyRequest;
export const OPTIONS = proxyRequest;
