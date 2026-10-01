import { useEffect, useState } from "react";
import type { Robot, Snapshot } from "./types";

/** Connection recovery is transport-only. A reconnect never resubmits a command. */
export function usePlatform() {
  const [robots, setRobots] = useState<Robot[]>([]);
  const [state, setState] = useState<Snapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const [catalogError, setCatalogError] = useState("");
  const [receivedAt, setReceivedAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setCatalogError("");
    fetch("/api/robots", { signal: abort.signal })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`Catalog unavailable (${response.status})`);
        return response.json();
      })
      .then((data) => setRobots(data.robots))
      .catch((error) => {
        if (!abort.signal.aborted) setCatalogError(error.message);
      });
    return () => abort.abort();
  }, [retry]);
  useEffect(() => {
    let disposed = false;
    let socket: WebSocket;
    let reconnect: ReturnType<typeof setTimeout>;
    const connect = () => {
      socket = new WebSocket(
        `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/events`,
      );
      socket.onmessage = (event) => {
        if (disposed) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === "snapshot" && Array.isArray(data.robots)) {
            setState(data);
            setReceivedAt(Date.now());
            setConnected(true);
          }
        } catch {
          setConnected(false);
        }
      };
      socket.onclose = () => {
        if (!disposed) {
          setConnected(false);
          reconnect = setTimeout(connect, 1800);
        }
      };
      socket.onerror = () => socket.close();
    };
    connect();
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => {
      disposed = true;
      clearTimeout(reconnect);
      clearInterval(timer);
      socket.close();
    };
  }, []);
  return {
    robots,
    state,
    live: connected && now - receivedAt < 2000,
    catalogError,
    reload: () => setRetry((value) => value + 1),
  };
}
