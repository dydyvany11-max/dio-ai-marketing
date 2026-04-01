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
    throw new Error(message);
  }

  return parsed;
}

function formatNumber(value) {
  return new Intl.NumberFormat("ru-RU").format(Number(value || 0));
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

function AnalyzeResultView({ data }) {
  if (!data) {
    return <div className="placeholder-panel">Запусти анализ группы, и результат появится здесь.</div>;
  }

  const metrics = data.metrics || {};
  const ai = data.ai || {};
  const status = data.ai_status || {};
  const competitors = data.competitors_found || [];
  const recommendations = data.recommendations || [];
  const topPosts = metrics.top_posts || [];

  return (
    <section className="result-view">
      <header className="result-header">
        <h3>{data?.source?.name || "Результат анализа"}</h3>
        <span className={`status-badge ${status.available ? "ok" : "warn"}`}>
          {status.message || "Статус неизвестен"}
        </span>
      </header>

      <div className="metrics-grid">
        <MetricCard label="Постов проанализировано" value={formatNumber(metrics.total_posts_analyzed)} />
        <MetricCard label="Средние просмотры" value={formatNumber(metrics.average_views)} />
        <MetricCard label="Средние лайки" value={formatNumber(metrics.average_likes)} />
        <MetricCard label="Средние комментарии" value={formatNumber(metrics.average_comments)} />
        <MetricCard label="Постов в день" value={metrics.posts_per_day || 0} />
      </div>

      <section className="block">
        <h4>Сводка</h4>
        <p>{ai.summary || "Нет краткой сводки"}</p>
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
        {topPosts.length ? (
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
                {topPosts.map((post) => (
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
          <p className="empty">Топ постов недоступен</p>
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

function GeneratedResultView({ data, editedText, onEditText }) {
  const [copyStatus, setCopyStatus] = useState("");
  const imageDataUrl =
    data?.generated_image_base64 && data?.generated_image_mime_type
      ? `data:${data.generated_image_mime_type};base64,${data.generated_image_base64}`
      : null;

  if (!data) {
    return <div className="placeholder-panel">Сгенерируй пост, и здесь появится редактор.</div>;
  }

  const chunks = data.knowledge_chunks || [];

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

      <section className="block editor-wrap">
        <div className="editor-head">
          <h4>Текст (можно редактировать вручную)</h4>
          <div className="editor-actions">
            <span className="muted">Символов: {formatNumber((editedText || "").length)}</span>
            <button type="button" className="secondary-btn" onClick={handleCopy}>
              Копировать
            </button>
          </div>
        </div>
        <textarea
          className="generated-editor"
          value={editedText}
          onChange={(e) => onEditText(e.target.value)}
          rows={10}
        />
        {copyStatus ? <p className="copy-status">{copyStatus}</p> : null}
      </section>

      {data.image_prompt ? (
        <section className="block">
          <h4>Промпт для изображения</h4>
          <p>{data.image_prompt}</p>
        </section>
      ) : null}

      {data.content_type === "image" ? (
        <section className="block">
          <h4>Сгенерированное изображение</h4>
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
  const [analyzeForm, setAnalyzeForm] = useState({ source: "", post_limit: 30, language: "ru" });
  const [generateForm, setGenerateForm] = useState({
    prompt: "",
    theme: "",
    tone: "",
    content_type: "text",
    publish: false,
    length: "medium",
    language: "ru",
  });

  const [analyzeLoading, setAnalyzeLoading] = useState(false);
  const [generateLoading, setGenerateLoading] = useState(false);
  const [analyzeResult, setAnalyzeResult] = useState(null);
  const [generateResult, setGenerateResult] = useState(null);
  const [editedGeneratedText, setEditedGeneratedText] = useState("");
  const [analyzeError, setAnalyzeError] = useState("");
  const [generateError, setGenerateError] = useState("");

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

  async function onAnalyzeSubmit(event) {
    event.preventDefault();
    setAnalyzeError("");
    setAnalyzeLoading(true);
    try {
      const payload = {
        source: analyzeForm.source.trim(),
        post_limit: Number(analyzeForm.post_limit) || 30,
        language: analyzeForm.language || "ru",
      };
      const data = await postJson("/vk/group/analyze", payload);
      setAnalyzeResult(data);
    } catch (error) {
      setAnalyzeError(error.message || "Ошибка анализа");
    } finally {
      setAnalyzeLoading(false);
    }
  }

  async function onGenerateSubmit(event) {
    event.preventDefault();
    setGenerateError("");
    setGenerateLoading(true);
    try {
      const payload = {
        ...generateForm,
        prompt: generateForm.prompt.trim(),
        theme: generateForm.theme.trim() || null,
        tone: generateForm.tone.trim() || null,
      };
      const data = await postJson("/vk/posts/generate", payload);
      setGenerateResult(data);
      setEditedGeneratedText(data?.text || "");
    } catch (error) {
      setGenerateError(error.message || "Ошибка генерации");
    } finally {
      setGenerateLoading(false);
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
        </nav>
      </header>

      {activeTab === "analyze" ? (
        <section className="module">
          <div className="module-head">
            <h2>Анализ группы</h2>
          </div>
          <form onSubmit={onAnalyzeSubmit} className="form">
            <label>
              Ссылка / screen_name / id
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
            </div>

            <button type="submit" disabled={analyzeLoading}>
              {analyzeLoading ? "Анализируем..." : "Запустить анализ"}
            </button>
          </form>
          {analyzeError ? <p className="error">{analyzeError}</p> : null}
          <AnalyzeResultView data={analyzeResult} />
        </section>
      ) : (
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
            </div>

            <button type="submit" disabled={generateLoading}>
              {generateLoading ? "Генерируем..." : "Сгенерировать"}
            </button>
          </form>
          {generateError ? <p className="error">{generateError}</p> : null}
          <GeneratedResultView
            data={generateResult}
            editedText={editedGeneratedText}
            onEditText={setEditedGeneratedText}
          />
        </section>
      )}
    </main>
  );
}
