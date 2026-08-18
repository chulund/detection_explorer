import { useEffect, useId, useRef, useState } from 'react';

/**
 * The small shapes the dashboard repeats.
 *
 * They were being written out by hand in four panels, which is how a chip in one place
 * drifts from a chip in another. Nothing here is clever; it exists so the drift stops.
 */

export function Chip({ on, children, ...rest }) {
  return (
    <button type="button" className={on ? 'chip chip-on' : 'chip'} {...rest}>
      {children}
    </button>
  );
}

export function Badge({ tone, children }) {
  return <span className={tone ? `badge badge-${tone}` : 'badge'}>{children}</span>;
}

export function Swatch({ colour, round }) {
  return (
    <span
      className={round ? 'legend-swatch round' : 'swatch'}
      style={{ background: colour }}
      aria-hidden="true"
    />
  );
}

/** Ready, queried but empty, or unavailable. Three states, three colours, no text. */
export function StatusDot({ status }) {
  const label = { present: 'has records', empty: 'queried, no records in window',
                  unavailable: 'source unavailable' }[status] ?? status;
  return <span className={`status-dot is-${status}`} title={label} role="img"
               aria-label={label} />;
}

/** One question, mutually exclusive answers, all of them visible at once. */
export function SegmentedControl({ value, options, onChange, label }) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          title={option.hint}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** A label and its value. Values are monospace unless they are prose. */
export function Field({ label, value, text }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div className="detail-row">
      <span className="detail-label">{label}</span>
      <span className={text ? 'detail-value text' : 'detail-value'}>{String(value)}</span>
    </div>
  );
}

export function FieldGroup({ title, children }) {
  return (
    <>
      {title && <div className="section-title">{title}</div>}
      {children}
    </>
  );
}

/** An accordion section. Open state lives with the caller, so it can be remembered. */
export function Collapsible({ title, aside, open, onToggle, children }) {
  return (
    <section className="panel">
      <button type="button" className="panel-head" aria-expanded={open} onClick={onToggle}>
        <span>{title}</span>
        {aside}
        <span className="disclosure" aria-hidden="true">{open ? '▾' : '▸'}</span>
      </button>
      {open && <div className="panel-body">{children}</div>}
    </section>
  );
}

/**
 * Hover or focus for the long version.
 *
 * This is where the paragraphs that used to sit permanently in the sidebar went. They are
 * still exact and still driven by the data; they are just no longer shouted at someone
 * who already knows what an experimental footprint is.
 */
export function Tooltip({ text, alignRight, children }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span
      className="tip"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="tip-target"
        aria-describedby={open ? id : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(event) => { event.preventDefault(); setOpen((was) => !was); }}
      >
        {children}
      </button>
      {open && (
        <span id={id} role="tooltip"
              className={alignRight ? 'tip-bubble align-right' : 'tip-bubble'}>
          {text}
        </span>
      )}
    </span>
  );
}

/** A modal sheet. Escape closes it, so does the backdrop; the card itself does not. */
export function Sheet({ title, open, onClose, children }) {
  const card = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    card.current?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={card}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="sheet-head">
          <h2>{title}</h2>
          <button type="button" className="sheet-close" onClick={onClose}
                  aria-label="Close">×</button>
        </div>
        <div className="sheet-body">{children}</div>
      </div>
    </div>
  );
}
