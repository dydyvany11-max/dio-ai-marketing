import { useEffect, useRef, useState } from "react";
import "./styles.css";

const BRAND_LOGO_URL =
  "http://80.93.62.177:8000/media/images/Logo_bez_fona_bez_teksta.width-80.height-80.png";

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const raw = await response.text();
  let parsed;
  try {
    parsed = raw ? JSON.parse(raw) : null;
  } catch {
    parsed = { raw };
  }

  if (!response.ok) {
    const message = parsed?.detail || parsed?.raw || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  return parsed;
}

async function getJson(url) {
  const response = await fetch(url, {
    method: "GET",
    headers: { "Accept": "application/json" },
  });

  const raw = await response.text();
  let parsed;
  try {
    parsed = raw ? JSON.parse(raw) : null;
  } catch {
    parsed = { raw };
  }

  if (!response.ok) {
    const message = parsed?.detail || parsed?.raw || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return parsed;
}

async function deleteJson(url) {
  const response = await fetch(url, {
    method: "DELETE",
    headers: { Accept: "application/json" },
  });

  const raw = await response.text();
  let parsed;
  try {
    parsed = raw ? JSON.parse(raw) : null;
  } catch {
    parsed = { raw };
  }

  if (!response.ok) {
    const message = parsed?.detail || parsed?.raw || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return parsed;
}

async function postFormData(url, formData) {
  const response = await fetch(url, {
    method: "POST",
    body: formData,
  });

  const raw = await response.text();
  let parsed;
  try {
    parsed = raw ? JSON.parse(raw) : null;
  } catch {
    parsed = { raw };
  }

  if (!response.ok) {
    const message = parsed?.detail || parsed?.raw || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  return parsed;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetriableHttpError(error) {
  const status = Number(error?.status || 0);
  if ([408, 409, 425, 429, 500, 502, 503, 504].includes(status)) return true;
  const message = String(error?.message || "").toLowerCase();
  return (
    message.includes("timeout") ||
    message.includes("timed out") ||
    message.includes("temporar") ||
    message.includes("dns") ||
    message.includes("connection reset") ||
    message.includes("connection aborted") ||
    message.includes("network error")
  );
}

async function postJsonWithRetry(url, payload, options = {}) {
  const attempts = Math.max(1, Number(options.attempts || 4));
  const baseDelayMs = Math.max(200, Number(options.baseDelayMs || 800));
  let lastError;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await postJson(url, payload);
    } catch (error) {
      lastError = error;
      const canRetry = attempt < attempts && isRetriableHttpError(error);
      if (!canRetry) {
        break;
      }
      await sleep(baseDelayMs * attempt);
    }
  }
  throw lastError;
}

async function getJsonWithRetry(url, options = {}) {
  const attempts = Math.max(1, Number(options.attempts || 4));
  const baseDelayMs = Math.max(200, Number(options.baseDelayMs || 800));
  let lastError;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await getJson(url);
    } catch (error) {
      lastError = error;
      const canRetry = attempt < attempts && isRetriableHttpError(error);
      if (!canRetry) {
        break;
      }
      await sleep(baseDelayMs * attempt);
    }
  }
  throw lastError;
}

async function deleteJsonWithRetry(url, options = {}) {
  const attempts = Math.max(1, Number(options.attempts || 3));
  const baseDelayMs = Math.max(200, Number(options.baseDelayMs || 700));
  let lastError;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await deleteJson(url);
    } catch (error) {
      lastError = error;
      const canRetry = attempt < attempts && isRetriableHttpError(error);
      if (!canRetry) {
        break;
      }
      await sleep(baseDelayMs * attempt);
    }
  }
  throw lastError;
}

function formatNumber(value) {
  return new Intl.NumberFormat("ru-RU").format(Number(value || 0));
}

function formatMoney(value, currency = "RUB") {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  try {
    return new Intl.NumberFormat("ru-RU", {
      style: "currency",
      currency: String(currency || "RUB").toUpperCase(),
      minimumFractionDigits: 4,
      maximumFractionDigits: 4,
    }).format(amount);
  } catch {
    return `${amount.toFixed(4)} ${currency || ""}`.trim();
  }
}

function formatDate(ts) {
  const value = Number(ts || 0);
  if (!value) return "—";
  const date = new Date(value * 1000);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function prettyContentType(contentType) {
  const map = {
    text: "Текст",
    story: "Сторис",
    image: "Текст + изображение",
    video: "Видео",
  };
  return map[contentType] || contentType;
}

function MetricCard({ label, value }) {
  return (
    <article className="metric-card">
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
    </article>
  );
}

function FancySelect({ value, onChange, options }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const selected = options.find((item) => item.value === value) || options[0];

  useEffect(() => {
    function handleOutsideClick(event) {
      if (!wrapRef.current?.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  return (
    <div className={`fancy-select ${open ? "open" : ""}`} ref={wrapRef}>
      <button
        type="button"
        className="fancy-select-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span>{selected?.label}</span>
        <span className="fancy-select-caret" />
      </button>
      {open ? (
        <div className="fancy-select-menu" role="listbox">
          {options.map((item) => (
            <button
              key={item.value}
              type="button"
              className={`fancy-select-option ${item.value === value ? "active" : ""}`}
              onClick={() => {
                onChange(item.value);
                setOpen(false);
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ConfirmActionButton({
  label,
  confirmLabel = "Точно удалить?",
  yesLabel = "Да",
  noLabel = "Нет",
  disabled = false,
  pending = false,
  onConfirm,
  className = "secondary-btn",
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    function handleOutsideClick(event) {
      if (!wrapRef.current?.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  return (
    <div className="confirm-wrap" ref={wrapRef}>
      <button
        type="button"
        className={className}
        disabled={disabled || pending}
        onClick={() => setOpen((prev) => !prev)}
      >
        {pending ? "Удаляем..." : label}
      </button>
      {open ? (
        <div className="confirm-popover">
          <p>{confirmLabel}</p>
          <div className="confirm-actions">
            <button
              type="button"
              className="secondary-btn danger-btn"
              disabled={pending}
              onClick={async () => {
                try {
                  await onConfirm?.();
                } finally {
                  setOpen(false);
                }
              }}
            >
              {yesLabel}
            </button>
            <button
              type="button"
              className="secondary-btn"
              disabled={pending}
              onClick={() => setOpen(false)}
            >
              {noLabel}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function KnowledgeBaseManager({
  items,
  loading,
  error,
  textForm,
  urlForm,
  fileForm,
  submittingText,
  submittingUrl,
  submittingFile,
  deletingDocumentId,
  fileInputKey,
  onRefresh,
  onTextFormChange,
  onUrlFormChange,
  onFileFormChange,
  onSubmitText,
  onSubmitUrl,
  onSubmitFile,
  onDeleteDocument,
}) {
  const [addMode, setAddMode] = useState("text");
  const activeItem = items.find((item) => item?.is_active) || items[0] || null;

  return (
    <section className="block">
      <div className="editor-head">
        <h4>База знаний</h4>
        <button
          type="button"
          className="secondary-btn"
          onClick={onRefresh}
          disabled={loading || submittingText || submittingUrl || submittingFile || !!deletingDocumentId}
        >
          {loading ? "Обновляем..." : "Обновить"}
        </button>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {activeItem ? (
        <p className="muted">
          Активная база: <strong>{activeItem.name}</strong> · язык: {activeItem.language} · файлов:{" "}
          {activeItem.files?.length || 0}
        </p>
      ) : (
        <p className="empty">База знаний пока пустая. Добавь текст, ссылку или файл.</p>
      )}

      <div className="kb-mode-tabs">
        <button
          type="button"
          className={`secondary-btn ${addMode === "text" ? "kb-mode-active" : ""}`}
          onClick={() => setAddMode("text")}
        >
          Текст
        </button>
        <button
          type="button"
          className={`secondary-btn ${addMode === "url" ? "kb-mode-active" : ""}`}
          onClick={() => setAddMode("url")}
        >
          Ссылка
        </button>
        <button
          type="button"
          className={`secondary-btn ${addMode === "file" ? "kb-mode-active" : ""}`}
          onClick={() => setAddMode("file")}
        >
          Файл
        </button>
        <button
          type="button"
          className={`secondary-btn ${addMode === "image" ? "kb-mode-active" : ""}`}
          onClick={() => setAddMode("image")}
        >
          Картинка
        </button>
      </div>

      {addMode === "text" ? (
        <form className="form kb-form" onSubmit={onSubmitText}>
          <h5>Добавить текст</h5>
          <label>
            Текст
            <textarea
              rows={5}
              value={textForm.content}
              onChange={(e) => onTextFormChange("content", e.target.value)}
              placeholder="Правила, шаблоны, ограничения..."
              required
            />
          </label>
          <button type="submit" disabled={submittingText}>
            {submittingText ? "Сохраняем..." : "Сохранить текст"}
          </button>
        </form>
      ) : null}

      {addMode === "url" ? (
        <form className="form kb-form" onSubmit={onSubmitUrl}>
          <h5>Добавить ссылку</h5>
          <label>
            URL
            <input
              value={urlForm.url}
              onChange={(e) => onUrlFormChange("url", e.target.value)}
              placeholder="https://example.com/article"
              required
            />
          </label>
          <label>
            Заголовок (опционально)
            <input
              value={urlForm.title}
              onChange={(e) => onUrlFormChange("title", e.target.value)}
              placeholder="Название документа"
            />
          </label>
          <button type="submit" disabled={submittingUrl}>
            {submittingUrl ? "Добавляем..." : "Добавить ссылку"}
          </button>
        </form>
      ) : null}

      {addMode === "file" ? (
        <form className="form kb-form" onSubmit={onSubmitFile}>
          <h5>Добавить файл</h5>
          <label>
            Файл
            <input
              key={`${fileInputKey}-file`}
              type="file"
              accept=".txt,.md,.csv,.json,.yml,.yaml,.ini,.log,.xml,.html,.htm,.pdf"
              onChange={(e) => onFileFormChange("file", e.target.files?.[0] || null)}
              required
            />
          </label>
          <button type="submit" disabled={submittingFile}>
            {submittingFile ? "Загружаем..." : "Загрузить файл"}
          </button>
        </form>
      ) : null}

      {addMode === "image" ? (
        <form className="form kb-form" onSubmit={onSubmitFile}>
          <h5>Добавить картинку</h5>
          <div className="row">
            <label>
              Подпись к изображению
              <input
                value={fileForm.image_caption}
                onChange={(e) => onFileFormChange("image_caption", e.target.value)}
                placeholder="Коротко опиши, что на изображении"
              />
            </label>
          </div>
          <label>
            Картинка
            <input
              key={`${fileInputKey}-image`}
              type="file"
              accept=".png,.jpg,.jpeg,.webp,.bmp,.gif"
              onChange={(e) => onFileFormChange("file", e.target.files?.[0] || null)}
              required
            />
          </label>
          <button type="submit" disabled={submittingFile}>
            {submittingFile ? "Загружаем..." : "Загрузить картинку"}
          </button>
        </form>
      ) : null}

      {items.length ? (
        <div className="cards">
          {items.map((item) => (
            <article key={item.id} className="card">
              <strong>
                {item.name} {item.is_active ? "· активная" : ""}
              </strong>
              <p className="muted">
                Язык: {item.language} · символов: {formatNumber(item.content_length || 0)}
              </p>
              {!item.files?.length ? (
                <p className="empty">Нет загруженных файлов</p>
              ) : (
                <div className="kb-files">
                  {item.files.map((doc) => (
                    <div key={doc.id} className="kb-file-row">
                      <div>
                        <p>{doc.title || doc.filename}</p>
                        <p className="muted">
                          {doc.source_type} · {doc.filename}
                        </p>
                      </div>
                      <ConfirmActionButton
                        label="Удалить"
                        className="secondary-btn danger-btn"
                        confirmLabel="Удалить документ из базы знаний?"
                        pending={deletingDocumentId === doc.id}
                        onConfirm={() => onDeleteDocument(doc.id, item.id)}
                      />
                    </div>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function AnalyzeResultView({ data }) {
  if (!data) {
    return <div className="placeholder-panel">Запусти анализ группы, и результат появится здесь.</div>;
  }

  const metrics = data.metrics || {};
  const ai = data.ai || {};
  const status = data.ai_status || {};
  const competitors = data.competitors_found || [];
  const recommendations = data.recommendations || [];
  const aiUsage = data.ai_usage || null;
  const topPosts = metrics.top_posts || [];
  const metricCards = [
    { key: "total_posts_analyzed", label: "Постов проанализировано", value: Number(metrics.total_posts_analyzed || 0) },
    { key: "average_views", label: "Средние просмотры", value: Number(metrics.average_views || 0) },
    { key: "average_likes", label: "Средние лайки", value: Number(metrics.average_likes || 0) },
    { key: "average_comments", label: "Средние комментарии", value: Number(metrics.average_comments || 0) },
    { key: "posts_per_day", label: "Постов в день", value: Number(metrics.posts_per_day || 0) },
  ].filter((item) => item.value > 0);
  const visibleTopPosts = topPosts.filter((post) => {
    const views = Number(post?.views || 0);
    const likes = Number(post?.likes || 0);
    const comments = Number(post?.comments || 0);
    const reposts = Number(post?.reposts || 0);
    return views > 0 || likes > 0 || comments > 0 || reposts > 0;
  });

  return (
    <section className="result-view">
      <header className="result-header">
        <h3>{data?.source?.name || "Результат анализа"}</h3>
        <span className={`status-badge ${status.available ? "ok" : "warn"}`}>
          {status.message || "Статус неизвестен"}
        </span>
      </header>

      {metricCards.length ? (
        <div className="metrics-grid">
          {metricCards.map((item) => (
            <MetricCard
              key={item.key}
              label={item.label}
              value={item.key === "posts_per_day" ? item.value : formatNumber(item.value)}
            />
          ))}
        </div>
      ) : (
        <section className="block">
          <p>Метрики недоступны или равны 0 (например, закрытая группа или ограниченный доступ).</p>
        </section>
      )}

      <section className="block">
        <h4>Сводка</h4>
        <p>
          {typeof ai.summary === "string"
            ? ai.summary || "Нет краткой сводки"
            : JSON.stringify(ai.summary || "") || "Нет краткой сводки"}
        </p>
      </section>

      <section className="block">
        <h4>Теги поиска конкурентов</h4>
        <div className="chips">
          {(ai.search_tags || []).length ? (
            ai.search_tags.map((tag) => (
              <span key={tag} className="chip">
                {tag}
              </span>
            ))
          ) : (
            <span className="empty">Теги не выделены</span>
          )}
        </div>
      </section>

      {aiUsage ? (
        <section className="block">
          <h4>AI usage</h4>
          <div className="chips">
            <span className="chip">Provider: {aiUsage.provider || "-"}</span>
            {aiUsage.model ? <span className="chip">Model: {aiUsage.model}</span> : null}
          </div>
          <p>
            prompt_tokens: <strong>{formatNumber(aiUsage.input_tokens || 0)}</strong> · completion_tokens:{" "}
            <strong>{formatNumber(aiUsage.output_tokens || 0)}</strong> · total_tokens:{" "}
            <strong>{formatNumber(aiUsage.total_tokens || 0)}</strong>
          </p>
          <p className="muted">
            Estimated cost:{" "}
            {aiUsage.estimated_cost != null
              ? formatMoney(aiUsage.estimated_cost, aiUsage.currency || "RUB")
              : "Pricing is not configured (set per-1k token prices in .env)"}
          </p>
        </section>
      ) : null}

      <section className="block two-col">
        <div>
          <h4>Интересы аудитории</h4>
          <ul className="plain-list">
            {(ai.audience_interests || []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4>Активность аудитории</h4>
          <ul className="plain-list">
            {(ai.audience_activity || []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className="block">
        <h4>Топ постов</h4>
        {visibleTopPosts.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Дата</th>
                  <th>Просмотры</th>
                  <th>Лайки</th>
                  <th>Комментарии</th>
                </tr>
              </thead>
              <tbody>
                {visibleTopPosts.map((post) => (
                  <tr key={post.post_id}>
                    <td>{post.post_id}</td>
                    <td>{formatDate(post.date)}</td>
                    <td>{formatNumber(post.views)}</td>
                    <td>{formatNumber(post.likes)}</td>
                    <td>{formatNumber(post.comments)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty">Топ постов недоступен или все метрики по постам равны 0</p>
        )}
      </section>

      <section className="block">
        <h4>Найденные конкуренты</h4>
        {competitors.length ? (
          <div className="cards">
            {competitors.map((item) => (
              <article key={`${item.screen_name || item.group_id}`} className="card">
                <strong>{item.name}</strong>
                <p className="muted">@{item.screen_name || "unknown"}</p>
                <p className="muted">Схожесть: {item.similarity_score}</p>
                <p>{item.why_similar}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="empty">Пока конкуренты не найдены</p>
        )}
      </section>

      <section className="block">
        <h4>Рекомендации</h4>
        {recommendations.length ? (
          <div className="cards">
            {recommendations.map((item, index) => (
              <article key={`${item.title}-${index}`} className="card">
                <strong>{item.title}</strong>
                <p>{item.action}</p>
                <p className="muted">{item.rationale}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="empty">Рекомендации отсутствуют</p>
        )}
      </section>
    </section>
  );
}

function AnalyzeHistoryView({
  items,
  loading,
  error,
  onOpenItem,
  onDeleteItem,
  deletingItemId,
  openItemLoadingId,
  onClearHistory,
  clearLoading,
}) {
  return (
    <section className="block">
      <div className="editor-head">
        <h4>История анализов</h4>
        <ConfirmActionButton
          label="Очистить историю"
          confirmLabel="Удалить всю историю анализов?"
          disabled={loading || !items.length}
          pending={clearLoading}
          onConfirm={onClearHistory}
        />
      </div>
      {error ? <p className="error">{error}</p> : null}
      {!loading && !items.length ? (
        <p className="empty">История пока пустая</p>
      ) : (
        <div className="cards">
          {items.map((item) => (
            <article key={item.id} className="card">
              <div className="card-head">
                <span />
                <ConfirmActionButton
                  label="Удалить"
                  className="secondary-btn danger-btn card-delete-btn"
                  confirmLabel="Удалить эту запись?"
                  pending={deletingItemId === item.id}
                  onConfirm={() => onDeleteItem(item.id)}
                />
              </div>
              <strong>{item.group_name || item.source_input || `Анализ #${item.id}`}</strong>
              <p className="muted">
                {item.screen_name ? `@${item.screen_name}` : "Без screen_name"} ·{" "}
                {item.created_at ? new Date(item.created_at).toLocaleString("ru-RU") : "—"}
              </p>
              <p className="muted">
                Постов: {formatNumber(item.total_posts_analyzed || 0)} · Лайки:{" "}
                {formatNumber(item.average_likes || 0)} · Комм.: {formatNumber(item.average_comments || 0)}
              </p>
              {item.ai_summary ? <p>{item.ai_summary}</p> : null}
              <button
                type="button"
                className="secondary-btn"
                onClick={() => onOpenItem(item.id)}
                disabled={openItemLoadingId === item.id}
              >
                {openItemLoadingId === item.id ? "Открываем..." : "Открыть результат"}
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function GenerateHistoryView({
  items,
  loading,
  error,
  onOpenItem,
  onDeleteItem,
  deletingItemId,
  openItemLoadingId,
  onClearHistory,
  clearLoading,
}) {
  return (
    <section className="block">
      <div className="editor-head">
        <h4>История генераций</h4>
        <ConfirmActionButton
          label="Очистить историю"
          confirmLabel="Удалить всю историю генераций?"
          disabled={loading || !items.length}
          pending={clearLoading}
          onConfirm={onClearHistory}
        />
      </div>
      {error ? <p className="error">{error}</p> : null}
      {!loading && !items.length ? (
        <p className="empty">История генераций пока пустая</p>
      ) : (
        <div className="cards">
          {items.map((item) => (
            <article key={item.id} className="card">
              <div className="card-head">
                <span />
                <ConfirmActionButton
                  label="Удалить"
                  className="secondary-btn danger-btn card-delete-btn"
                  confirmLabel="Удалить эту запись?"
                  pending={deletingItemId === item.id}
                  onConfirm={() => onDeleteItem(item.id)}
                />
              </div>
              <strong>{item.prompt || `Генерация #${item.id}`}</strong>
              <p className="muted">
                {item.created_at ? new Date(item.created_at).toLocaleString("ru-RU") : "—"} ·{" "}
                {prettyContentType(item.content_type || "text")}
              </p>
              <p className="muted">
                Символов: {formatNumber(item.char_count || 0)} · Слов: {formatNumber(item.word_count || 0)}
              </p>
              {item.text_preview ? <p>{item.text_preview}</p> : null}
              <button
                type="button"
                className="secondary-btn"
                onClick={() => onOpenItem(item.id)}
                disabled={openItemLoadingId === item.id}
              >
                {openItemLoadingId === item.id ? "Открываем..." : "Открыть"}
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function RecommendationsChatView({
  hasReport,
  messages,
  input,
  onInputChange,
  onSend,
  loading,
  blocked,
  error,
}) {
  if (!hasReport) return null;

  return (
    <section className="block">
      <div className="editor-head">
        <h4>План улучшения</h4>
      </div>

      <div className="chat-history">
        {messages.length ? (
          messages.map((message, index) => (
            <article
              key={`${message.role}-${index}`}
              className={`chat-message ${message.role === "user" ? "chat-message-user" : "chat-message-assistant"}`}
            >
              <p className="chat-role">{message.role === "user" ? "Вы" : "AI-стратег"}</p>
              <p>{message.text}</p>
            </article>
          ))
        ) : (
          <p className="empty">План появится после вашего вопроса.</p>
        )}
      </div>

      <div className="chat-input-row">
        <textarea
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          placeholder="Введите вопрос по улучшению"
          rows={3}
          disabled={blocked}
        />
        <button type="button" onClick={onSend} disabled={blocked || loading || !input.trim()}>
          {loading ? "Думаю..." : "Отправить"}
        </button>
      </div>
      {blocked ? <p className="muted">Дождитесь завершения текущего анализа, затем продолжайте чат.</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}

function GeneratedResultView({
  data,
  editedText,
  onEditText,
  editedImagePrompt,
  onEditImagePrompt,
  onRegenerateImage,
  regenerateImageLoading,
  regenerateImageError,
  onPublishEdited,
  publishLoading,
  publishError,
  publishSuccess,
}) {
  const [copyStatus, setCopyStatus] = useState("");
  const imageDataUrl =
    data?.generated_image_base64 && data?.generated_image_mime_type
      ? `data:${data.generated_image_mime_type};base64,${data.generated_image_base64}`
      : null;

  if (!data) {
    return <div className="placeholder-panel">Сгенерируй пост, и здесь появится редактор.</div>;
  }

  const chunks = data.knowledge_chunks || [];
  const aiUsage = data?.ai_usage || null;

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(editedText || "");
      setCopyStatus("Скопировано");
      setTimeout(() => setCopyStatus(""), 1400);
    } catch {
      setCopyStatus("Не удалось скопировать");
      setTimeout(() => setCopyStatus(""), 1600);
    }
  }

  function handleImageDownload() {
    if (!imageDataUrl) return;
    const mime = (data?.generated_image_mime_type || "").toLowerCase();
    const extension = mime.includes("jpeg") ? "jpg" : mime.includes("webp") ? "webp" : "png";
    const link = document.createElement("a");
    link.href = imageDataUrl;
    link.download = `generated-image.${extension}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  return (
    <section className="result-view">
      <header className="result-header">
        <h3>Готовый контент</h3>
        <span className={`status-badge ${data.published ? "ok" : "plain"}`}>
          {data.published ? "Опубликовано" : "Черновик"}
        </span>
      </header>

      <div className="chips">
        <span className="chip">Тип: {prettyContentType(data.content_type)}</span>
        {data.theme ? <span className="chip">Тема: {data.theme}</span> : null}
        {data.tone ? <span className="chip">Тон: {data.tone}</span> : null}
      </div>

      {aiUsage ? (
        <section className="block">
          <h4>AI usage</h4>
          <div className="chips">
            <span className="chip">Provider: {aiUsage.provider || "-"}</span>
            {aiUsage.model ? <span className="chip">Model: {aiUsage.model}</span> : null}
          </div>
          <p>
            Input: <strong>{formatNumber(aiUsage.input_tokens || 0)}</strong> ? Output:{" "}
            <strong>{formatNumber(aiUsage.output_tokens || 0)}</strong> ? Total:{" "}
            <strong>{formatNumber(aiUsage.total_tokens || 0)}</strong>
          </p>
          <p className="muted">
            Estimated cost:{" "}
            {aiUsage.estimated_cost != null
              ? formatMoney(aiUsage.estimated_cost, aiUsage.currency || "RUB")
              : "Pricing is not configured (set per-1k token prices in .env)"}
          </p>
        </section>
      ) : null}

      <section className="block editor-wrap">
        <div className="editor-head">
          <h4>Текст</h4>
          <div className="editor-actions">
            <span className="muted">Символов: {formatNumber((editedText || "").length)}</span>
            <button type="button" className="secondary-btn" onClick={handleCopy}>
              Копировать
            </button>
            {!data.published ? (
              <button
                type="button"
                onClick={onPublishEdited}
                disabled={publishLoading || !(editedText || "").trim()}
              >
                {publishLoading ? "Публикуем..." : "Опубликовать"}
              </button>
            ) : null}
          </div>
        </div>
        <textarea
          className="generated-editor"
          value={editedText}
          onChange={(e) => onEditText(e.target.value)}
          rows={10}
        />
        {copyStatus ? <p className="copy-status">{copyStatus}</p> : null}
        {publishError ? <p className="error">{publishError}</p> : null}
        {publishSuccess ? <p className="copy-status">{publishSuccess}</p> : null}
      </section>

      {data.content_type === "image" ? (
        <section className="block editor-wrap">
          <div className="editor-head">
            <h4>Промпт для изображения</h4>
            <div className="editor-actions">
              <button
                type="button"
                onClick={onRegenerateImage}
                disabled={regenerateImageLoading || !(editedText || "").trim()}
              >
                {regenerateImageLoading ? "Генерируем изображение..." : "Перегенерировать изображение"}
              </button>
            </div>
          </div>
          <textarea
            className="generated-editor"
            value={editedImagePrompt}
            onChange={(e) => onEditImagePrompt(e.target.value)}
            rows={5}
            placeholder="Можно оставить пустым: тогда промпт соберётся автоматически из текста поста"
          />
          {regenerateImageError ? <p className="error">{regenerateImageError}</p> : null}
        </section>
      ) : null}

      {data.content_type === "image" ? (
        <section className="block">
          <h4>Сгенерированное изображение</h4>
          <p className="muted">
            {Number(data?.image_reference_files_attached || 0) > 0
              ? `Фото-референсов отправлено в модель: ${Number(data?.image_reference_files_attached || 0)}`
              : "Фото-референсы не были прикреплены в запросе генерации"}
          </p>
          {imageDataUrl ? (
            <div className="generated-image-wrap">
              <img src={imageDataUrl} alt="Сгенерированное изображение" className="generated-image-preview" />
              <button type="button" className="secondary-btn" onClick={handleImageDownload}>
                Скачать изображение
              </button>
            </div>
          ) : (
            <p className="empty">Изображение не получено. Попробуй сгенерировать ещё раз.</p>
          )}
        </section>
      ) : null}

      {data.video_script ? (
        <section className="block">
          <h4>Сценарий видео</h4>
          <p>{data.video_script}</p>
        </section>
      ) : null}

      {chunks.length ? (
        <section className="block">
          <h4>Использованные материалы базы знаний</h4>
          <div className="cards">
            {chunks.map((chunk, idx) => (
              <article key={`${chunk.filename || chunk.title}-${idx}`} className="card">
                <strong>{chunk.title || chunk.filename || "Фрагмент"}</strong>
                <p className="muted">Оценка: {chunk.score}</p>
                <p className="muted">{chunk.reason}</p>
                {chunk.snippet_preview ? <p>{chunk.snippet_preview}</p> : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState("analyze");
  const [analyzeForm, setAnalyzeForm] = useState({
    source: "",
    post_limit: 30,
    language: "ru",
    ai_provider: "auto",
  });
  const [generateForm, setGenerateForm] = useState({
    prompt: "",
    theme: "",
    tone: "",
    content_type: "text",
    publish: false,
    length: "medium",
    language: "ru",
    ai_provider: "auto",
    use_kb_image_references: true,
  });

  const [analyzeLoading, setAnalyzeLoading] = useState(false);
  const [generateLoading, setGenerateLoading] = useState(false);
  const [analyzeResult, setAnalyzeResult] = useState(null);
  const [analyzeHistoryVisible, setAnalyzeHistoryVisible] = useState(false);
  const [analyzeHistoryItems, setAnalyzeHistoryItems] = useState([]);
  const [analyzeHistoryLoading, setAnalyzeHistoryLoading] = useState(false);
  const [analyzeHistoryError, setAnalyzeHistoryError] = useState("");
  const [analyzeHistoryClearLoading, setAnalyzeHistoryClearLoading] = useState(false);
  const [analyzeHistoryDeleteLoadingId, setAnalyzeHistoryDeleteLoadingId] = useState(null);
  const [openHistoryItemLoadingId, setOpenHistoryItemLoadingId] = useState(null);
  const [analyzeCurrentHistoryId, setAnalyzeCurrentHistoryId] = useState(null);
  const [recommendationsChatMessages, setRecommendationsChatMessages] = useState([]);
  const [recommendationsChatInput, setRecommendationsChatInput] = useState("");
  const [recommendationsChatLoading, setRecommendationsChatLoading] = useState(false);
  const [recommendationsChatError, setRecommendationsChatError] = useState("");
  const [generateResult, setGenerateResult] = useState(null);
  const [generateHistoryVisible, setGenerateHistoryVisible] = useState(false);
  const [generateHistoryItems, setGenerateHistoryItems] = useState([]);
  const [generateHistoryLoading, setGenerateHistoryLoading] = useState(false);
  const [generateHistoryError, setGenerateHistoryError] = useState("");
  const [generateHistoryClearLoading, setGenerateHistoryClearLoading] = useState(false);
  const [generateHistoryDeleteLoadingId, setGenerateHistoryDeleteLoadingId] = useState(null);
  const [openGenerateHistoryItemLoadingId, setOpenGenerateHistoryItemLoadingId] = useState(null);
  const [generateCurrentHistoryId, setGenerateCurrentHistoryId] = useState(null);
  const [editedGeneratedText, setEditedGeneratedText] = useState("");
  const [editedImagePrompt, setEditedImagePrompt] = useState("");
  const [analyzeError, setAnalyzeError] = useState("");
  const [generateError, setGenerateError] = useState("");
  const [publishEditedLoading, setPublishEditedLoading] = useState(false);
  const [publishEditedError, setPublishEditedError] = useState("");
  const [publishEditedSuccess, setPublishEditedSuccess] = useState("");
  const [regenerateImageLoading, setRegenerateImageLoading] = useState(false);
  const [regenerateImageError, setRegenerateImageError] = useState("");
  const [knowledgeItems, setKnowledgeItems] = useState([]);
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [knowledgeError, setKnowledgeError] = useState("");
  const [knowledgeTextForm, setKnowledgeTextForm] = useState({
    content: "",
    language: "ru",
  });
  const [knowledgeUrlForm, setKnowledgeUrlForm] = useState({
    url: "",
    title: "",
    language: "ru",
  });
  const [knowledgeFileForm, setKnowledgeFileForm] = useState({
    language: "ru",
    image_caption: "",
    file: null,
  });
  const [knowledgeSubmitTextLoading, setKnowledgeSubmitTextLoading] = useState(false);
  const [knowledgeSubmitUrlLoading, setKnowledgeSubmitUrlLoading] = useState(false);
  const [knowledgeSubmitFileLoading, setKnowledgeSubmitFileLoading] = useState(false);
  const [knowledgeDeleteLoadingId, setKnowledgeDeleteLoadingId] = useState("");
  const [knowledgeFileInputKey, setKnowledgeFileInputKey] = useState(0);
  const historyLoadInFlightRef = useRef(false);
  const generationHistoryLoadInFlightRef = useRef(false);

  const languageOptions = [
    { value: "ru", label: "Русский" },
    { value: "en", label: "English" },
  ];
  const contentTypeOptions = [
    { value: "text", label: "Текст" },
    { value: "story", label: "Сторис" },
    { value: "image", label: "Текст + изображение" },
    { value: "video", label: "Видео" },
  ];
  const lengthOptions = [
    { value: "short", label: "Короткая" },
    { value: "medium", label: "Средняя" },
    { value: "long", label: "Длинная" },
  ];
  const publishOptions = [
    { value: "no", label: "Нет" },
    { value: "yes", label: "Да" },
  ];
  const aiProviderOptions = [
    { value: "auto", label: "Авто" },
    { value: "gigachat", label: "GigaChat" },
    { value: "yandex", label: "YandexGPT" },
  ];

  useEffect(() => {
    onLoadKnowledgeBases();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onAnalyzeSubmit(event) {
    event.preventDefault();
    setAnalyzeError("");
    setAnalyzeHistoryError("");
    setRecommendationsChatError("");
    setRecommendationsChatMessages([]);
    setRecommendationsChatInput("");
    setAnalyzeCurrentHistoryId(null);
    setAnalyzeLoading(true);
    try {
      const payload = {
        source: analyzeForm.source.trim(),
        post_limit: Number(analyzeForm.post_limit) || 30,
        language: analyzeForm.language || "ru",
        ai_provider: analyzeForm.ai_provider || "auto",
      };
      const data = await postJsonWithRetry("/vk/group/analyze", payload, { attempts: 4, baseDelayMs: 900 });
      setAnalyzeResult(data);
      setAnalyzeCurrentHistoryId(Number(data?.history_id) || null);
      // If a new analysis replaced previous report, start chat context from this report.
      setRecommendationsChatMessages([]);
      setRecommendationsChatInput("");
      setRecommendationsChatError("");
      onLoadAnalyzeHistory();
    } catch (error) {
      setAnalyzeError(error.message || "Ошибка анализа после нескольких попыток");
    } finally {
      setAnalyzeLoading(false);
    }
  }

  async function onLoadKnowledgeBases() {
    setKnowledgeError("");
    setKnowledgeLoading(true);
    try {
      const data = await getJsonWithRetry("/vk/knowledge", { attempts: 3, baseDelayMs: 650 });
      setKnowledgeItems(Array.isArray(data?.items) ? data.items : []);
    } catch (error) {
      setKnowledgeError(error.message || "Не удалось загрузить базу знаний");
    } finally {
      setKnowledgeLoading(false);
    }
  }

  function onChangeKnowledgeTextForm(field, value) {
    setKnowledgeTextForm((prev) => ({ ...prev, [field]: value }));
  }

  function onChangeKnowledgeUrlForm(field, value) {
    setKnowledgeUrlForm((prev) => ({ ...prev, [field]: value }));
  }

  function onChangeKnowledgeFileForm(field, value) {
    setKnowledgeFileForm((prev) => ({ ...prev, [field]: value }));
  }

  async function onSubmitKnowledgeText(event) {
    event.preventDefault();
    setKnowledgeError("");
    setKnowledgeSubmitTextLoading(true);
    try {
      const payload = {
        name: "Основная база знаний",
        content: (knowledgeTextForm.content || "").trim(),
        language: knowledgeTextForm.language || "ru",
      };
      await postJsonWithRetry("/vk/knowledge/upload", payload, { attempts: 3, baseDelayMs: 700 });
      setKnowledgeTextForm((prev) => ({ ...prev, content: "" }));
      await onLoadKnowledgeBases();
    } catch (error) {
      setKnowledgeError(error.message || "Не удалось сохранить текст в базу знаний");
    } finally {
      setKnowledgeSubmitTextLoading(false);
    }
  }

  async function onSubmitKnowledgeUrl(event) {
    event.preventDefault();
    setKnowledgeError("");
    setKnowledgeSubmitUrlLoading(true);
    try {
      const payload = {
        url: (knowledgeUrlForm.url || "").trim(),
        title: (knowledgeUrlForm.title || "").trim() || null,
        language: knowledgeUrlForm.language || "ru",
      };
      await postJsonWithRetry("/vk/knowledge/upload-url", payload, { attempts: 3, baseDelayMs: 700 });
      setKnowledgeUrlForm((prev) => ({ ...prev, url: "", title: "" }));
      await onLoadKnowledgeBases();
    } catch (error) {
      setKnowledgeError(error.message || "Не удалось добавить ссылку в базу знаний");
    } finally {
      setKnowledgeSubmitUrlLoading(false);
    }
  }

  async function onSubmitKnowledgeFile(event) {
    event.preventDefault();
    if (!knowledgeFileForm.file) {
      setKnowledgeError("Выберите файл для загрузки");
      return;
    }

    setKnowledgeError("");
    setKnowledgeSubmitFileLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", knowledgeFileForm.file);
      formData.append("language", knowledgeFileForm.language || "ru");
      if ((knowledgeFileForm.image_caption || "").trim()) {
        formData.append("image_caption", knowledgeFileForm.image_caption.trim());
      }
      await postFormData("/vk/knowledge/upload-file", formData);
      setKnowledgeFileForm((prev) => ({
        ...prev,
        file: null,
        image_caption: "",
      }));
      setKnowledgeFileInputKey((prev) => prev + 1);
      await onLoadKnowledgeBases();
    } catch (error) {
      setKnowledgeError(error.message || "Не удалось загрузить файл в базу знаний");
    } finally {
      setKnowledgeSubmitFileLoading(false);
    }
  }

  async function onDeleteKnowledgeDocument(documentId, knowledgeBaseId) {
    if (!documentId) return;

    setKnowledgeError("");
    setKnowledgeDeleteLoadingId(documentId);
    try {
      const query = knowledgeBaseId
        ? `?knowledge_base_id=${encodeURIComponent(knowledgeBaseId)}`
        : "";
      await deleteJsonWithRetry(`/vk/knowledge/files/${encodeURIComponent(documentId)}${query}`, {
        attempts: 3,
        baseDelayMs: 650,
      });
      await onLoadKnowledgeBases();
    } catch (error) {
      setKnowledgeError(error.message || "Не удалось удалить документ");
    } finally {
      setKnowledgeDeleteLoadingId("");
    }
  }

  async function onLoadAnalyzeHistory() {
    if (analyzeHistoryClearLoading) return;
    if (historyLoadInFlightRef.current) return;
    historyLoadInFlightRef.current = true;
    setAnalyzeHistoryError("");
    setAnalyzeHistoryLoading(true);
    try {
      const data = await getJsonWithRetry("/vk/group/analyze/history?limit=30", { attempts: 4, baseDelayMs: 900 });
      setAnalyzeHistoryItems(Array.isArray(data?.items) ? data.items : []);
    } catch (error) {
      setAnalyzeHistoryError(error.message || "Не удалось загрузить историю анализов");
    } finally {
      setAnalyzeHistoryLoading(false);
      historyLoadInFlightRef.current = false;
    }
  }

  async function onToggleAnalyzeHistory() {
    const nextVisible = !analyzeHistoryVisible;
    setAnalyzeHistoryVisible(nextVisible);
    if (nextVisible) {
      await onLoadAnalyzeHistory();
    }
  }

  async function onClearAnalyzeHistory() {
    if (!analyzeHistoryItems.length || analyzeHistoryClearLoading) return;

    setAnalyzeHistoryError("");
    setAnalyzeHistoryClearLoading(true);
    try {
      await deleteJsonWithRetry("/vk/group/analyze/history", { attempts: 3, baseDelayMs: 700 });
      setAnalyzeHistoryItems([]);
      setAnalyzeCurrentHistoryId(null);
      setRecommendationsChatMessages([]);
      setRecommendationsChatInput("");
      setOpenHistoryItemLoadingId(null);
      setAnalyzeHistoryVisible(false);
    } catch (error) {
      setAnalyzeHistoryError(error.message || "Не удалось очистить историю");
    } finally {
      setAnalyzeHistoryClearLoading(false);
      setAnalyzeHistoryLoading(false);
      historyLoadInFlightRef.current = false;
    }
  }

  async function onOpenAnalyzeHistoryItem(historyId) {
    setAnalyzeHistoryError("");
    setRecommendationsChatError("");
    setRecommendationsChatInput("");
    setOpenHistoryItemLoadingId(historyId);
    try {
      const data = await getJsonWithRetry(`/vk/group/analyze/history/${historyId}`, { attempts: 4, baseDelayMs: 900 });
      if (data?.report) {
        setAnalyzeResult(data.report);
        setAnalyzeCurrentHistoryId(Number(data?.id || historyId) || null);
        if (Array.isArray(data?.chat_messages)) {
          setRecommendationsChatMessages(
            data.chat_messages
              .map((item) => ({
                role: item?.role === "assistant" ? "assistant" : "user",
                text: String(item?.text || "").trim(),
              }))
              .filter((item) => item.text),
          );
        } else {
          setRecommendationsChatMessages([]);
        }
      }
    } catch (error) {
      setAnalyzeHistoryError(error.message || "Не удалось открыть запись истории");
    } finally {
      setOpenHistoryItemLoadingId(null);
    }
  }

  async function onDeleteAnalyzeHistoryItem(historyId) {
    if (!historyId || analyzeHistoryDeleteLoadingId === historyId) return;

    setAnalyzeHistoryError("");
    setAnalyzeHistoryDeleteLoadingId(historyId);
    try {
      await deleteJsonWithRetry(`/vk/group/analyze/history/${historyId}`, { attempts: 3, baseDelayMs: 650 });
      setAnalyzeHistoryItems((prev) => prev.filter((item) => item.id !== historyId));
      if (analyzeCurrentHistoryId === historyId) {
        setAnalyzeCurrentHistoryId(null);
        setRecommendationsChatMessages([]);
      }
    } catch (error) {
      setAnalyzeHistoryError(error.message || "Не удалось удалить запись истории");
    } finally {
      setAnalyzeHistoryDeleteLoadingId(null);
    }
  }

  async function onLoadGenerateHistory() {
    if (generateHistoryClearLoading) return;
    if (generationHistoryLoadInFlightRef.current) return;
    generationHistoryLoadInFlightRef.current = true;
    setGenerateHistoryError("");
    setGenerateHistoryLoading(true);
    try {
      const data = await getJsonWithRetry("/vk/posts/generate/history?limit=30", { attempts: 4, baseDelayMs: 900 });
      setGenerateHistoryItems(Array.isArray(data?.items) ? data.items : []);
    } catch (error) {
      setGenerateHistoryError(error.message || "Не удалось загрузить историю генераций");
    } finally {
      setGenerateHistoryLoading(false);
      generationHistoryLoadInFlightRef.current = false;
    }
  }

  async function onToggleGenerateHistory() {
    const nextVisible = !generateHistoryVisible;
    setGenerateHistoryVisible(nextVisible);
    if (nextVisible) {
      await onLoadGenerateHistory();
    }
  }

  async function onClearGenerateHistory() {
    if (!generateHistoryItems.length || generateHistoryClearLoading) return;

    setGenerateHistoryError("");
    setGenerateHistoryClearLoading(true);
    try {
      await deleteJsonWithRetry("/vk/posts/generate/history", { attempts: 3, baseDelayMs: 700 });
      setGenerateHistoryItems([]);
      setGenerateCurrentHistoryId(null);
      setOpenGenerateHistoryItemLoadingId(null);
      setGenerateHistoryVisible(false);
    } catch (error) {
      setGenerateHistoryError(error.message || "Не удалось очистить историю генераций");
    } finally {
      setGenerateHistoryClearLoading(false);
      setGenerateHistoryLoading(false);
      generationHistoryLoadInFlightRef.current = false;
    }
  }

  async function onOpenGenerateHistoryItem(historyId) {
    setGenerateHistoryError("");
    setOpenGenerateHistoryItemLoadingId(historyId);
    try {
      const data = await getJsonWithRetry(`/vk/posts/generate/history/${historyId}`, {
        attempts: 4,
        baseDelayMs: 900,
      });
      if (data?.report) {
        setGenerateResult(data.report);
        setGenerateCurrentHistoryId(Number(data?.id || historyId) || null);
        setEditedGeneratedText(data?.report?.text || "");
        setEditedImagePrompt(data?.report?.image_prompt || "");
        setGenerateForm((prev) => ({
          ...prev,
          prompt: String(data?.prompt || "").trim(),
          theme: String(data?.theme || data?.report?.theme || "").trim(),
          tone: String(data?.tone || data?.report?.tone || "").trim(),
          content_type: String(data?.content_type || data?.report?.content_type || prev.content_type || "text"),
          language: String(data?.language || prev.language || "ru"),
          length: String(data?.length || prev.length || "medium"),
          publish: Boolean(data?.publish_requested),
          ai_provider: prev.ai_provider || "auto",
        }));
      }
    } catch (error) {
      setGenerateHistoryError(error.message || "Не удалось открыть запись генерации");
    } finally {
      setOpenGenerateHistoryItemLoadingId(null);
    }
  }

  async function onDeleteGenerateHistoryItem(historyId) {
    if (!historyId || generateHistoryDeleteLoadingId === historyId) return;

    setGenerateHistoryError("");
    setGenerateHistoryDeleteLoadingId(historyId);
    try {
      await deleteJsonWithRetry(`/vk/posts/generate/history/${historyId}`, { attempts: 3, baseDelayMs: 650 });
      setGenerateHistoryItems((prev) => prev.filter((item) => item.id !== historyId));
      if (generateCurrentHistoryId === historyId) {
        setGenerateCurrentHistoryId(null);
      }
    } catch (error) {
      setGenerateHistoryError(error.message || "Не удалось удалить запись истории");
    } finally {
      setGenerateHistoryDeleteLoadingId(null);
    }
  }

  async function onSendRecommendationsChat() {
    const message = (recommendationsChatInput || "").trim();
    if (!message || !analyzeResult || recommendationsChatLoading) {
      return;
    }

    setRecommendationsChatError("");
    setRecommendationsChatLoading(true);
    setRecommendationsChatMessages((prev) => [...prev, { role: "user", text: message }]);
    setRecommendationsChatInput("");

    try {
      const data = await postJsonWithRetry(
        "/vk/group/recommendations/chat",
        {
          report: analyzeResult,
          message,
          language: analyzeForm.language || "ru",
          history_id: analyzeCurrentHistoryId || null,
        },
        { attempts: 3, baseDelayMs: 800 },
      );
      const answer = String(data?.answer || "").trim();
      if (!answer) {
        throw new Error("Пустой ответ от AI");
      }
      if (Array.isArray(data?.chat_messages) && data.chat_messages.length) {
        setRecommendationsChatMessages(
          data.chat_messages
            .map((item) => ({
              role: item?.role === "assistant" ? "assistant" : "user",
              text: String(item?.text || "").trim(),
            }))
            .filter((item) => item.text),
        );
      } else {
        setRecommendationsChatMessages((prev) => [...prev, { role: "assistant", text: answer }]);
      }
    } catch (error) {
      setRecommendationsChatError(error.message || "Не удалось получить подробный план");
      setRecommendationsChatMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Не получилось получить ответ. Попробуйте отправить запрос еще раз." },
      ]);
    } finally {
      setRecommendationsChatLoading(false);
    }
  }

  async function onGenerateSubmit(event) {
    event.preventDefault();
    setGenerateError("");
    setPublishEditedError("");
    setPublishEditedSuccess("");
    setRegenerateImageError("");
    setGenerateLoading(true);
    try {
      const payload = {
        ...generateForm,
        prompt: generateForm.prompt.trim(),
        theme: generateForm.theme.trim() || null,
        tone: generateForm.tone.trim() || null,
        ai_provider: generateForm.ai_provider || "auto",
      };
      const data = await postJsonWithRetry("/vk/posts/generate", payload, { attempts: 4, baseDelayMs: 900 });
      setGenerateResult(data);
      setGenerateCurrentHistoryId(Number(data?.history_id) || null);
      setEditedGeneratedText(data?.text || "");
      setEditedImagePrompt(data?.image_prompt || "");
      if (generateHistoryVisible) {
        onLoadGenerateHistory();
      }
    } catch (error) {
      setGenerateError(error.message || "Ошибка генерации после нескольких попыток");
    } finally {
      setGenerateLoading(false);
    }
  }

  async function onRegenerateImage() {
    const postText = (editedGeneratedText || generateResult?.text || "").trim();
    if (!postText) {
      setRegenerateImageError("Нет текста поста для генерации изображения.");
      return;
    }
    setRegenerateImageError("");
    setRegenerateImageLoading(true);
    try {
      const data = await postJsonWithRetry("/vk/posts/regenerate-image", {
        post_text: postText,
        image_prompt: (editedImagePrompt || "").trim() || null,
        theme: generateResult?.theme || generateForm.theme || null,
        tone: generateResult?.tone || generateForm.tone || null,
        language: generateForm.language || "ru",
        ai_provider: generateForm.ai_provider || "auto",
        use_kb_image_references: Boolean(generateForm.use_kb_image_references),
      });
      setGenerateResult((prev) =>
        prev
          ? {
              ...prev,
              image_prompt: data.image_prompt,
              generated_image_base64: data.generated_image_base64,
              generated_image_mime_type: data.generated_image_mime_type,
              knowledge_chunks_used: Number(data?.knowledge_chunks_used || 0),
              knowledge_chunks: Array.isArray(data?.knowledge_chunks) ? data.knowledge_chunks : prev.knowledge_chunks,
              image_reference_files_attached: Number(data?.image_reference_files_attached || 0),
            }
          : prev,
      );
      setEditedImagePrompt(data.image_prompt || "");
    } catch (error) {
      setRegenerateImageError(error.message || "Не удалось перегенерировать изображение.");
    } finally {
      setRegenerateImageLoading(false);
    }
  }

  async function onPublishEditedPost() {
    const message = (editedGeneratedText || "").trim();
    if (!message) {
      setPublishEditedError("Текст пустой, нечего публиковать.");
      return;
    }

    setPublishEditedError("");
    setPublishEditedSuccess("");
    setPublishEditedLoading(true);
    try {
      const result = await postJson("/vk/posts/publish", { message });
      setGenerateResult((prev) =>
        prev
          ? {
              ...prev,
              text: message,
              published: true,
              post_id: result?.post_id ?? prev.post_id,
              owner_id: result?.owner_id ?? prev.owner_id,
              publish_note: prev.publish_note || "Опубликовано вручную после редактирования.",
            }
          : prev,
      );
      setPublishEditedSuccess("Пост успешно опубликован.");
    } catch (error) {
      setPublishEditedError(error.message || "Не удалось опубликовать пост.");
    } finally {
      setPublishEditedLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="brand-strip">
        <div className="brand-strip-left">
          <img className="brand-logo" src={BRAND_LOGO_URL} alt="Лого ДИО-Консалт" loading="lazy" />
          <div>
            <p className="eyebrow">ДИО-Консалт</p>
            <p className="brand-subline">VK Аналитика + Контент-студия</p>
          </div>
        </div>
        <nav className="top-nav">
          <button
            type="button"
            className={`nav-btn ${activeTab === "analyze" ? "nav-btn-active" : ""}`}
            onClick={() => setActiveTab("analyze")}
          >
            Анализ VK-групп
          </button>
          <button
            type="button"
            className={`nav-btn ${activeTab === "generate" ? "nav-btn-active" : ""}`}
            onClick={() => setActiveTab("generate")}
          >
            Генерация контента
          </button>
          <button
            type="button"
            className={`nav-btn ${activeTab === "knowledge" ? "nav-btn-active" : ""}`}
            onClick={() => setActiveTab("knowledge")}
          >
            База знаний
          </button>
        </nav>
      </header>

      {activeTab === "analyze" ? (
        <section className="module">
          <div className="module-head">
            <h2>Анализ группы VK</h2>
          </div>
          <form onSubmit={onAnalyzeSubmit} className="form">
            <label>
              Ссылка на группу / screen_name / id
              <input
                value={analyzeForm.source}
                onChange={(e) => setAnalyzeForm((s) => ({ ...s, source: e.target.value }))}
                placeholder="https://vk.com/diocon"
                required
              />
            </label>

            <div className="row">
              <label>
                Лимит постов
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={analyzeForm.post_limit}
                  onChange={(e) => setAnalyzeForm((s) => ({ ...s, post_limit: e.target.value }))}
                />
              </label>
              <label>
                Язык ответа
                <FancySelect
                  value={analyzeForm.language}
                  onChange={(nextValue) => setAnalyzeForm((s) => ({ ...s, language: nextValue }))}
                  options={languageOptions}
                />
              </label>
              <label>
                Нейросеть
                <FancySelect
                  value={analyzeForm.ai_provider}
                  onChange={(nextValue) => setAnalyzeForm((s) => ({ ...s, ai_provider: nextValue }))}
                  options={aiProviderOptions}
                />
              </label>
            </div>

            <div className="editor-actions">
              <button type="submit" disabled={analyzeLoading}>
                {analyzeLoading ? "Анализируем..." : "Запустить анализ"}
              </button>
              <button type="button" className="secondary-btn" onClick={onToggleAnalyzeHistory}>
                {analyzeHistoryVisible ? "Скрыть историю" : "История"}
              </button>
            </div>
          </form>
          {analyzeError ? <p className="error">{analyzeError}</p> : null}
          {analyzeHistoryVisible ? (
            <AnalyzeHistoryView
              items={analyzeHistoryItems}
              loading={analyzeHistoryLoading}
              error={analyzeHistoryError}
              onOpenItem={onOpenAnalyzeHistoryItem}
              onDeleteItem={onDeleteAnalyzeHistoryItem}
              deletingItemId={analyzeHistoryDeleteLoadingId}
              openItemLoadingId={openHistoryItemLoadingId}
              onClearHistory={onClearAnalyzeHistory}
              clearLoading={analyzeHistoryClearLoading}
            />
          ) : null}
          <AnalyzeResultView data={analyzeResult} />
          <RecommendationsChatView
            hasReport={Boolean(analyzeResult)}
            messages={recommendationsChatMessages}
            input={recommendationsChatInput}
            onInputChange={setRecommendationsChatInput}
            onSend={onSendRecommendationsChat}
            loading={recommendationsChatLoading}
            blocked={analyzeLoading}
            error={recommendationsChatError}
          />
        </section>
      ) : activeTab === "generate" ? (
        <section className="module">
          <div className="module-head">
            <h2>Генерация поста</h2>
          </div>
          <form onSubmit={onGenerateSubmit} className="form">
            <label>
              Промпт
              <textarea
                value={generateForm.prompt}
                onChange={(e) => setGenerateForm((s) => ({ ...s, prompt: e.target.value }))}
                placeholder="Напиши пост про внедрение 1С для малого бизнеса"
                rows={5}
                required
              />
            </label>

            <div className="row">
              <label>
                Тема
                <input
                  value={generateForm.theme}
                  onChange={(e) => setGenerateForm((s) => ({ ...s, theme: e.target.value }))}
                  placeholder="автоматизация"
                />
              </label>
              <label>
                Тон
                <input
                  value={generateForm.tone}
                  onChange={(e) => setGenerateForm((s) => ({ ...s, tone: e.target.value }))}
                  placeholder="деловой"
                />
              </label>
            </div>

            <div className="row">
              <label>
                Тип контента
                <FancySelect
                  value={generateForm.content_type}
                  onChange={(nextValue) => setGenerateForm((s) => ({ ...s, content_type: nextValue }))}
                  options={contentTypeOptions}
                />
              </label>

              <label>
                Длина
                <FancySelect
                  value={generateForm.length}
                  onChange={(nextValue) => setGenerateForm((s) => ({ ...s, length: nextValue }))}
                  options={lengthOptions}
                />
              </label>
            </div>

            <div className="row compact">
              <label>
                Язык ответа
                <FancySelect
                  value={generateForm.language}
                  onChange={(nextValue) => setGenerateForm((s) => ({ ...s, language: nextValue }))}
                  options={languageOptions}
                />
              </label>
              <label>
                Сразу публиковать
                <FancySelect
                  value={generateForm.publish ? "yes" : "no"}
                  onChange={(nextValue) =>
                    setGenerateForm((s) => ({
                      ...s,
                      publish: nextValue === "yes",
                    }))
                  }
                  options={publishOptions}
                />
              </label>
              <label>
                Нейросеть
                <FancySelect
                  value={generateForm.ai_provider}
                  onChange={(nextValue) => setGenerateForm((s) => ({ ...s, ai_provider: nextValue }))}
                  options={aiProviderOptions}
                />
              </label>
            </div>

            {generateForm.content_type === "image" ? (
              <div className="row compact">
                <label>
                  Учитывать фото-референсы из базы знаний
                  <FancySelect
                    value={generateForm.use_kb_image_references ? "yes" : "no"}
                    onChange={(nextValue) =>
                      setGenerateForm((s) => ({
                        ...s,
                        use_kb_image_references: nextValue === "yes",
                      }))
                    }
                    options={publishOptions}
                  />
                </label>
              </div>
            ) : null}

            <div className="editor-actions">
              <button type="submit" disabled={generateLoading}>
                {generateLoading ? "Генерируем..." : "Сгенерировать"}
              </button>
              <button type="button" className="secondary-btn" onClick={onToggleGenerateHistory}>
                {generateHistoryVisible ? "Скрыть историю" : "История"}
              </button>
            </div>
          </form>
          {generateError ? <p className="error">{generateError}</p> : null}
          {generateHistoryVisible ? (
            <GenerateHistoryView
              items={generateHistoryItems}
              loading={generateHistoryLoading}
              error={generateHistoryError}
              onOpenItem={onOpenGenerateHistoryItem}
              onDeleteItem={onDeleteGenerateHistoryItem}
              deletingItemId={generateHistoryDeleteLoadingId}
              openItemLoadingId={openGenerateHistoryItemLoadingId}
              onClearHistory={onClearGenerateHistory}
              clearLoading={generateHistoryClearLoading}
            />
          ) : null}
          <GeneratedResultView
            data={generateResult}
            editedText={editedGeneratedText}
            onEditText={setEditedGeneratedText}
            editedImagePrompt={editedImagePrompt}
            onEditImagePrompt={setEditedImagePrompt}
            onRegenerateImage={onRegenerateImage}
            regenerateImageLoading={regenerateImageLoading}
            regenerateImageError={regenerateImageError}
            onPublishEdited={onPublishEditedPost}
            publishLoading={publishEditedLoading}
            publishError={publishEditedError}
            publishSuccess={publishEditedSuccess}
          />
        </section>
      ) : (
        <section className="module">
          <div className="module-head">
            <h2>База знаний</h2>
          </div>
          <KnowledgeBaseManager
            items={knowledgeItems}
            loading={knowledgeLoading}
            error={knowledgeError}
            textForm={knowledgeTextForm}
            urlForm={knowledgeUrlForm}
            fileForm={knowledgeFileForm}
            submittingText={knowledgeSubmitTextLoading}
            submittingUrl={knowledgeSubmitUrlLoading}
            submittingFile={knowledgeSubmitFileLoading}
            deletingDocumentId={knowledgeDeleteLoadingId}
            fileInputKey={knowledgeFileInputKey}
            onRefresh={onLoadKnowledgeBases}
            onTextFormChange={onChangeKnowledgeTextForm}
            onUrlFormChange={onChangeKnowledgeUrlForm}
            onFileFormChange={onChangeKnowledgeFileForm}
            onSubmitText={onSubmitKnowledgeText}
            onSubmitUrl={onSubmitKnowledgeUrl}
            onSubmitFile={onSubmitKnowledgeFile}
            onDeleteDocument={onDeleteKnowledgeDocument}
          />
        </section>
      )}
    </main>
  );
}
