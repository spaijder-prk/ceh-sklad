import { FormEvent, useEffect, useState } from "react";
import {
  UserAccess,
  UserRole,
  clearToken,
  loadUserAccess,
  updateUserAccess,
} from "./api";
import "./user-access.css";

const roleLabels: Record<UserRole, string> = {
  admin: "Администратор",
  manager: "Руководитель",
  representative: "Торговый представитель",
};

export function UserAccessView({ currentUserId }: { currentUserId: string }) {
  const [users, setUsers] = useState<UserAccess[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void loadUserAccess()
      .then((rows) => {
        if (!cancelled) setUsers(rows);
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Не удалось загрузить пользователей");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const applyChange = async (
    userId: string,
    payload: { isActive?: boolean; newPassword?: string },
    success: string,
  ): Promise<boolean> => {
    setBusyId(userId);
    setMessage(null);
    setError(null);
    try {
      const updated = await updateUserAccess(userId, payload);
      setUsers((rows) => rows.map((row) => (row.id === updated.id ? updated : row)));
      setMessage(success);

      if (userId === currentUserId && payload.newPassword) {
        clearToken();
        window.location.reload();
      }
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Изменение доступа не выполнено");
      return false;
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      {message && <div className="alert success">{message}</div>}
      {error && <div className="alert error">{error}</div>}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Доступ пользователей</h2>
            <p>Отключение учетной записи и смена пароля немедленно отзывают действующие токены пользователя.</p>
          </div>
        </div>

        <div className="table-wrap">
          <table className="user-access-table">
            <thead>
              <tr>
                <th>Пользователь</th>
                <th>Роль</th>
                <th>Статус</th>
                <th>Доступ</th>
                <th>Временный пароль</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <UserAccessRow
                  key={user.id}
                  user={user}
                  isCurrentUser={user.id === currentUserId}
                  busy={busyId === user.id}
                  onToggle={() =>
                    applyChange(
                      user.id,
                      { isActive: !user.is_active },
                      user.is_active ? "Учетная запись отключена" : "Учетная запись включена",
                    )
                  }
                  onReset={(newPassword) =>
                    applyChange(
                      user.id,
                      { newPassword },
                      user.id === currentUserId
                        ? "Пароль изменен. Выполняется повторный вход."
                        : "Временный пароль установлен; прежние токены отозваны",
                    )
                  }
                />
              ))}
            </tbody>
          </table>
        </div>
        {!loading && users.length === 0 && <div className="empty">Пользователей нет</div>}
        {loading && <div className="empty">Загрузка учетных записей…</div>}
      </section>
    </>
  );
}

function UserAccessRow({
  user,
  isCurrentUser,
  busy,
  onToggle,
  onReset,
}: {
  user: UserAccess;
  isCurrentUser: boolean;
  busy: boolean;
  onToggle: () => Promise<boolean>;
  onReset: (newPassword: string) => Promise<boolean>;
}) {
  const [password, setPassword] = useState("");
  const passwordValid = password.length >= 8;

  const resetPassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!passwordValid) return;
    const ok = await onReset(password);
    if (ok) setPassword("");
  };

  const cannotDisableSelf = isCurrentUser && user.is_active;

  return (
    <tr>
      <td>
        <strong>{user.full_name}</strong>
        <small>{user.email}{isCurrentUser ? " · текущая учетная запись" : ""}</small>
      </td>
      <td>{roleLabels[user.role]}</td>
      <td>
        {user.is_active
          ? <span className="status ok">активна</span>
          : <span className="status muted">отключена</span>}
      </td>
      <td>
        <button
          type="button"
          className={user.is_active ? "danger-button" : "secondary-button"}
          disabled={busy || cannotDisableSelf}
          title={cannotDisableSelf ? "Собственную учетную запись администратора отключить нельзя" : undefined}
          onClick={() => void onToggle()}
        >
          {busy ? "Изменение…" : user.is_active ? "Отключить" : "Включить"}
        </button>
      </td>
      <td>
        <form className="password-reset-form" onSubmit={resetPassword}>
          <input
            type="password"
            minLength={8}
            autoComplete="new-password"
            placeholder="Минимум 8 символов"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <button className="secondary-button" disabled={busy || !passwordValid}>
            {isCurrentUser ? "Сменить и выйти" : "Сбросить пароль"}
          </button>
        </form>
      </td>
    </tr>
  );
}
