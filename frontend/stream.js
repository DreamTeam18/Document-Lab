// Decode SSE incrementally: events and UTF-8 characters may span network chunks.
export async function readEvents(body, onEvent) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  function consume(final = false) {
    let boundary;
    while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
      const frame = buffer.slice(0, boundary.index);
      buffer = buffer.slice(boundary.index + boundary[0].length);
      dispatch(frame);
    }
    if (final && buffer.trim()) dispatch(buffer);
  }
  function dispatch(frame) {
    let name = "message";
    const data = [];
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith("event:")) name = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (data.length) onEvent(name, JSON.parse(data.join("\n")));
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      consume(done);
      if (done) break;
    }
  } finally { reader.releaseLock(); }
}
