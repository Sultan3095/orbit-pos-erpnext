import React, { useEffect, useState } from 'react';
import { t } from './i18n.js';
// Customer-facing second screen. Open /orbit-pos#display on the second monitor.
export default function Display() {
  const [s, setS] = useState({ lines: [], total: 0, lang: 'ar', theme: 'brand' });
  useEffect(() => {
    const ch = new BroadcastChannel('orbit-display');
    ch.onmessage = (e) => setS(e.data);
    return () => ch.close();
  }, []);
  useEffect(() => { document.documentElement.dataset.theme = ['brand', 'galaxy', 'light', 'dark'].includes(s.theme) ? s.theme : 'brand'; document.documentElement.dir = s.lang === 'ar' ? 'rtl' : 'ltr'; }, [s]);
  return (
    <div className="display">
      <h1>{t(s.lang, 'app')}</h1>
      {s.lines.length === 0 ? <p>{t(s.lang, 'thanks')}</p> : (
        <table><tbody>{s.lines.map((l, i) => (
          <tr key={i}><td>{l.name}</td><td>{l.qty} × {l.price.toFixed(2)}</td><td>{l.net.toFixed(2)}</td></tr>))}</tbody></table>)}
      <div className="big">{t(s.lang, 'total')}: {s.total.toFixed(2)}</div>
    </div>
  );
}
