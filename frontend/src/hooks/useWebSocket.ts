import { useEffect, useRef, useState } from "react";
import { WS_BASE_URL } from "../api/client";

export function useWebSocket<T = unknown>(path: string | null) {
  const [lastMessage, setLastMessage] = useState<T | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!path) return;

    const ws = new WebSocket(`${WS_BASE_URL}${path}`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (event) => {
      try {
        setLastMessage(JSON.parse(event.data));
      } catch {
        // ignore malformed messages
      }
    };

    return () => {
      ws.close();
    };
  }, [path]);

  return { lastMessage, connected };
}
