import { useEffect, useState } from "react";

const TOKEN_KEY = "ceh-admin-access-token";
const RECONNECT_DELAY_MS = 5_000;
const PING_INTERVAL_MS = 25_000;

export type RealtimeStatus = "offline" | "connecting" | "online";

interface TicketResponse {
  ticket: string;
  expires_in: number;
}

async function requestRealtimeTicket(): Promise<string> {
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (!token) throw new Error("Нет активной сессии");

  const response = await fetch("/api/v1/auth/ws-ticket", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error(`Не удалось получить WebSocket-ticket: ${response.status}`);
  return ((await response.json()) as TicketResponse).ticket;
}

function websocketUrl(ticket: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/v1/ws/browser-updates?ticket=${encodeURIComponent(ticket)}`;
}

export function useRealtimeUpdates(
  active: boolean,
  onChanged: (silent?: boolean) => Promise<void>,
): RealtimeStatus {
  const [status, setStatus] = useState<RealtimeStatus>("offline");

  useEffect(() => {
    if (!active) {
      setStatus("offline");
      return;
    }

    let stopped = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let pingTimer: number | null = null;

    const clearPing = () => {
      if (pingTimer !== null) window.clearInterval(pingTimer);
      pingTimer = null;
    };

    const scheduleReconnect = () => {
      if (stopped || reconnectTimer !== null) return;
      setStatus("offline");
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        void connect();
      }, RECONNECT_DELAY_MS);
    };

    const connect = async () => {
      if (stopped) return;
      setStatus("connecting");
      try {
        const ticket = await requestRealtimeTicket();
        if (stopped) return;

        socket = new WebSocket(websocketUrl(ticket));
        socket.onopen = () => {
          if (stopped) return;
          setStatus("online");
          clearPing();
          pingTimer = window.setInterval(() => {
            if (socket?.readyState === WebSocket.OPEN) socket.send("ping");
          }, PING_INTERVAL_MS);
        };
        socket.onmessage = (event) => {
          try {
            const payload = JSON.parse(String(event.data)) as { type?: string };
            if (payload.type === "state_changed" || payload.type === "catalog_changed") {
              void onChanged(true);
            }
          } catch {
            // Неизвестное сообщение не должно ронять канал обновлений.
          }
        };
        socket.onerror = () => socket?.close();
        socket.onclose = () => {
          clearPing();
          scheduleReconnect();
        };
      } catch {
        scheduleReconnect();
      }
    };

    void connect();
    return () => {
      stopped = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      clearPing();
      socket?.close(1000, "Экран закрыт");
    };
  }, [active, onChanged]);

  return status;
}
