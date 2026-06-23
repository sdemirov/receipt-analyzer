import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useIsNarrow } from "../useMedia.js";

const VAT = { "А": "А", "Б": "Б", "Г": "Г" };

export default function ReceiptModal({ rid, onClose, selectedIds = new Set(), onToggleProduct }) {
  const narrow = useIsNarrow();
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("items");
  const [error, setError] = useState(false);
  const [zoom, setZoom] = useState(1);   // image preview zoom factor (1 = fit width)

  useEffect(() => {
    setData(null);
    setError(false);
    setZoom(1);
    api.receipt(rid).then(setData).catch(() => setError(true));
  }, [rid]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Draggable floating panel (move it aside to keep watching the chart).
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const drag = useRef({ on: false, sx: 0, sy: 0, bx: 0, by: 0 });
  useEffect(() => {
    const move = (e) => {
      if (!drag.current.on) return;
      setPos({ x: drag.current.bx + (e.clientX - drag.current.sx),
               y: drag.current.by + (e.clientY - drag.current.sy) });
    };
    const up = () => { drag.current.on = false; document.body.style.userSelect = ""; };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, []);
  const startDrag = (e) => {
    if (narrow) return;
    drag.current = { on: true, sx: e.clientX, sy: e.clientY, bx: pos.x, by: pos.y };
    document.body.style.userSelect = "none";
  };

  const r = data?.receipt;
  const isImage = !!r?.source_pdf && /\.png$/i.test(r.source_pdf);

  return (
    <div className="modal-layer">
      <div className={`modal${narrow ? " modal-mobile" : " floating"}`}
        style={narrow ? undefined : { transform: `translate(${pos.x}px, ${pos.y}px)` }}>
        <button className="modal-close" onMouseDown={(e) => e.stopPropagation()} onClick={onClose}>×</button>

        {error && <div className="modal-body">Грешка при зареждане на бележката.</div>}
        {!data && !error && <div className="modal-body">Зареждане…</div>}

        {r && (
          <>
            <div className="modal-head drag-handle" onMouseDown={startDrag}
              title={narrow ? undefined : "Премести (влачи)"}>
              <h3>{r.store_name?.replace("Хипермаркет Кауфланд ", "") || "Бележка"}</h3>
              <div className="modal-meta">
                <span>{r.purchase_date} {r.purchase_time}</span>
                <span>Филиал {r.branch_id}</span>
                <span>{r.payment_method}</span>
                <span><b>{r.total?.toFixed(2)} €</b></span>
                {r.card_savings > 0 && <span className="save">карта −{r.card_savings.toFixed(2)}</span>}
                {r.promo_savings > 0 && <span className="save">промо −{r.promo_savings.toFixed(2)}</span>}
              </div>
            </div>

            <div className="modal-tabs">
              <button className={tab === "items" ? "on" : ""} onClick={() => setTab("items")}>Продукти</button>
              <button className={tab === "text" ? "on" : ""} onClick={() => setTab("text")}>Извлечен текст</button>
              <button className={tab === "pdf" ? "on" : ""} onClick={() => setTab("pdf")}>{isImage ? "Снимка" : "PDF"}</button>
            </div>

            <div className="modal-body">
              {tab === "items" && (
                <>
                  {onToggleProduct && (
                    <p className="items-hint">Кликни продукт, за да го добавиш/премахнеш в графиката.</p>
                  )}
                  <div className="table-scroll">
                  <table className="items-table">
                    <thead>
                      <tr><th>Продукт</th><th>Кол.</th><th>Ед. цена</th><th>Сума</th><th>ДДС</th></tr>
                    </thead>
                    <tbody>
                      {data.items.map((it, i) => {
                        const inChart = selectedIds.has(it.product_id);
                        return (
                          <tr key={i}
                            className={`${it.on_promo ? "promo " : ""}${onToggleProduct ? "clickable " : ""}${inChart ? "in-chart" : ""}`}
                            title={onToggleProduct ? (inChart ? "Премахни от графиката" : "Добави в графиката") : undefined}
                            onClick={() => onToggleProduct?.({
                              id: it.product_id, canonical_name: it.canonical_name,
                              unit_measure: it.unit_measure,
                            })}>
                            <td>{inChart ? "✓ " : ""}{it.raw_name}{it.on_promo ? " 🏷" : ""}</td>
                            <td>{it.unit_measure === "kg" ? `${it.qty} кг` : it.qty}</td>
                            <td>{it.unit_price.toFixed(2)}</td>
                            <td>{it.line_total.toFixed(2)}</td>
                            <td>{VAT[it.vat_class] || it.vat_class}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  </div>
                </>
              )}
              {tab === "text" && <pre className="receipt-text">{data.text || "(няма текст)"}</pre>}
              {tab === "pdf" && (
                <div className="pdf-view">
                  <div className="pdf-actions">
                    <a href={api.pdfUrl(rid)} target="_blank" rel="noreferrer">Отвори в нов раздел ↗</a>
                    <a href={api.pdfUrl(rid)} download={`${r.purchase_date || "receipt"}${isImage ? ".png" : ".pdf"}`}>⬇ Изтегли {isImage ? "снимка" : "PDF"}</a>
                    {isImage && (
                      <span className="img-zoom" onMouseDown={(e) => e.stopPropagation()}>
                        <button onClick={() => setZoom((z) => Math.max(1, +(z - 0.5).toFixed(2)))} disabled={zoom <= 1} title="Намали">−</button>
                        <span className="img-zoom-level">{Math.round(zoom * 100)}%</span>
                        <button onClick={() => setZoom((z) => Math.min(5, +(z + 0.5).toFixed(2)))} title="Увеличи">+</button>
                      </span>
                    )}
                  </div>
                  {isImage
                    ? <div className="img-scroll" style={{ overflow: "auto", maxHeight: "70vh" }}>
                        <img
                          alt="receipt"
                          src={api.pdfUrl(rid)}
                          onClick={() => setZoom((z) => (z >= 3 ? 1 : +(z + 1).toFixed(2)))}
                          style={{ width: `${zoom * 100}%`, cursor: zoom > 1 ? "zoom-out" : "zoom-in", display: "block" }}
                          title="Кликни за увеличение/намаление"
                        />
                      </div>
                    : <iframe className="pdf-frame" title="receipt pdf" src={api.pdfUrl(rid)} />}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
