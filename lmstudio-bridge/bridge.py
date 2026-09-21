import json
import http.server
import urllib.request
import urllib.error

UPSTREAM = "http://127.0.0.1:1234"
LOG = r"C:\Users\qudin\AppData\Local\Temp\opencode\claude-proxy4.log"
MAX_LOG_BODY = 1200


def fix_body(raw: bytes) -> bytes:
    try:
        data = json.loads(raw)
    except Exception:
        return raw
    if not isinstance(data, dict) or "messages" not in data:
        return raw
    msgs = data.get("messages", [])
    systems = []
    rest = []
    for msg in msgs:
        if isinstance(msg, dict) and msg.get("role") == "system":
            systems.append(msg)
        else:
            rest.append(msg)
    if not systems:
        return raw
    if isinstance(data.get("system"), str):
        systems.insert(0, {"role": "user", "content": data["system"]})
    elif isinstance(data.get("system"), list):
        systems.insert(0, {"role": "user", "content": data["system"]})
    new = dict(data)
    new["system"] = systems[0].get("content", [{"type": "text", "text": ""}])
    new["messages"] = rest
    return json.dumps(new, ensure_ascii=False).encode("utf-8")


class H(http.server.BaseHTTPRequestHandler):
    proto_version = "HTTP/1.1"

    def _log_request(self, path, body, status, resp):
        with open(LOG, "ab") as f:
            f.write(("=" * 50 + "\n").encode())
            f.write(f"{self.command} {path}\n".encode())
            f.write(b"BODY: ")
            f.write(body[:MAX_LOG_BODY])
            f.write(f"\nREWRITTEN: ".encode())
            f.write(fix_body(body)[:MAX_LOG_BODY])
            f.write(f"\n-> {status}\n".encode())
            f.write(resp[:1200])
            f.write(b"\n")

    def _forward(self, path, method, body=None):
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "content-length", "accept-encoding")}
        req = urllib.request.Request(UPSTREAM + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                resp = r.read()
                status = r.status
        except urllib.error.HTTPError as e:
            resp = e.read()
            status = e.code
        return status, resp

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        out = fix_body(body) if self.path.startswith("/v1/messages") else body
        status, resp = self._forward(self.path, "POST", out)
        self._log_request(self.path, body, status, resp)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def do_GET(self):
        status, resp = self._forward(self.path, "GET", None)
        self._log_request(self.path, b"", status, resp)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    http.server.HTTPServer(("127.0.0.1", 8098), H).serve_forever()