"""A stub of the Anthropic Messages API for probing Claude Code at no cost.

Every request body is written to `req/` beside this file. A message request is answered with the
text `OK`, or, while `script.json` beside this file holds entries and the request offers tools,
with the first entry as one `tool_use` (the entry is then consumed). Run it with the port as the
only argument, and point `ANTHROPIC_BASE_URL` at it (`cc.sh` does).
"""

import itertools
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REQUESTS = os.path.join(HERE, "req")
SCRIPT = os.path.join(HERE, "script.json")
COUNTER = itertools.count(1)


def sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def answers_a_tool(request: dict) -> bool:
    content = request["messages"][-1].get("content")
    return isinstance(content, list) and any(c.get("type") == "tool_result" for c in content)


def next_block(request: dict, number: int) -> dict:
    if not (os.path.exists(SCRIPT) and request.get("tools")) or answers_a_tool(request):
        return {"type": "text", "text": "OK"}
    with open(SCRIPT) as handle:
        script = json.load(handle)
    if not script:
        return {"type": "text", "text": "OK"}
    with open(SCRIPT, "w") as handle:
        json.dump(script[1:], handle)
    entry = script[0]
    return {
        "type": "tool_use",
        "id": f"toolu_{number:04d}",
        "name": entry["name"],
        "input": entry["input"],
    }


def events(message: dict, block: dict, stop: str) -> list[bytes]:
    if block["type"] == "text":
        start = {"type": "text", "text": ""}
        delta = {"type": "text_delta", "text": block["text"]}
    else:
        start = {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}
        delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
    return [
        sse("message_start", {"type": "message_start", "message": message}),
        sse(
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": start},
        ),
        sse("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": delta}),
        sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
        sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop, "stop_sequence": None},
                "usage": {"output_tokens": 1},
            },
        ),
        sse("message_stop", {"type": "message_stop"}),
    ]


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.end_headers()

    def do_GET(self) -> None:
        self.send_json({"data": [], "has_more": False})

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b""
        number = next(COUNTER)
        name = f"{number:04d}{self.path.split('?')[0].replace('/', '_')}.json"
        with open(os.path.join(REQUESTS, name), "wb") as handle:
            handle.write(raw)
        if "count_tokens" in self.path:
            return self.send_json({"input_tokens": 10})
        if not self.path.startswith("/v1/messages"):
            return self.send_json({})
        request = json.loads(raw or b"{}")
        block = next_block(request, number)
        stop = "tool_use" if block["type"] == "tool_use" else "end_turn"
        message = {
            "id": f"msg_{number}",
            "type": "message",
            "role": "assistant",
            "model": request.get("model", "stub"),
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        if not request.get("stream"):
            return self.send_json({**message, "content": [block], "stop_reason": stop})
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for chunk in events(message, block, stop):
            self.wfile.write(chunk)
        return None

    def send_json(self, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    os.makedirs(REQUESTS, exist_ok=True)
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Stub).serve_forever()
