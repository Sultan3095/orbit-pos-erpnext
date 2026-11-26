import React, { useEffect, useRef } from 'react';
import JsBarcode from 'jsbarcode';

const fmt = (n) => (Math.round((Number(n) + Number.EPSILON) * 100) / 100).toFixed(2);
const B = (ar, en) => `${ar} / ${en}`;

function Barcode({ value }) {
  const ref = useRef(null);
  useEffect(() => { if (ref.current && value) { try { JsBarcode(ref.current, value, { format: 'CODE128', height: 48, width: 1.6, displayValue: true, fontSize: 14, margin: 0 }); } catch (e) {} } }, [value]);
  return <svg ref={ref} data-testid="barcode" />;
}

// 80mm bilingual receipt. Two designs chosen per POS Profile: one for the sale, one for a return / exchange.
// The window and the terms always come from Orbit POS Settings (never hard-coded here).
export default function Receipt({ data, onClose }) {
  const d = data;
  const compact = /compact/i.test(d.format || '');
  const detailed = /detailed/i.test(d.format || '');
  const ex = d.exchange_receipt;
  return (
    <div className="receipt-overlay" data-testid="receipt-modal">
      <div className="receipt-tools no-print">
        <button className="primary" onClick={() => window.print()} data-testid="print-btn">{B('طباعة', 'Print')}</button>
        <button onClick={onClose} data-testid="receipt-close">{B('إغلاق', 'Close')}</button>
      </div>
      <div className={'receipt-sheet' + (compact ? ' compact' : '') + (d.is_return ? ' ret' : '')} data-testid="receipt-sheet">
        <div className="r-center r-title">{d.company}</div>
        {d.branch ? <div className="r-center">{d.branch}</div> : null}
        <div className="r-center r-sub">{d.is_return ? B('إيصال مرتجع / استبدال', 'Return / Exchange Receipt') : B('فاتورة بيع', 'Sales Invoice')}</div>
        <div className="r-row"><span>{B('رقم', 'No.')}</span><b>{d.invoice}</b></div>
        {d.against ? <div className="r-row"><span>{B('عن الفاتورة', 'Against')}</span><b>{d.against}</b></div> : null}
        <div className="r-row"><span>{B('التاريخ', 'Date')}</span><span>{d.date} {d.time}</span></div>
        <div className="r-row"><span>{B('الكاشير', 'Cashier')}</span><span>{d.cashier}</span></div>
        <div className="r-row" data-testid="r-customer"><span>{B('العميل', 'Customer')}</span><b>{d.customer}</b></div>
        <hr />
        <table>
          <tbody>
            {d.lines.map((l, i) => (
              <React.Fragment key={i}>
                <tr><td colSpan="3">{l.name}{l.promo ? ' *' : ''}</td></tr>
                <tr className="r-num"><td>{Math.abs(l.qty)} x {fmt(l.rate)}</td>{detailed || !compact ? <td></td> : <td></td>}<td className="r-end">{fmt(l.amount)}</td></tr>
                {l.serial ? <tr className="r-small"><td colSpan="3">S/N: {l.serial}</td></tr> : null}
              </React.Fragment>))}
          </tbody>
        </table>
        <hr />
        {d.discount ? <div className="r-row"><span>{B('خصم', 'Discount')}</span><span>{fmt(d.discount)}</span></div> : null}
        {d.coupon ? <div className="r-row" data-testid="r-coupon"><span>{B('كوبون', 'Coupon')} {d.coupon}</span><span>-{fmt(d.coupon_amount)}</span></div> : null}
        {d.taxes.map((t, i) => <div className="r-row" key={i}><span>{t.name}</span><span>{fmt(t.amount)}</span></div>)}
        <div className="r-row r-total"><span>{d.is_return ? B('إجمالي المرتجع', 'Return total') : B('الإجمالي', 'Total')}</span><b>{fmt(Math.abs(d.grand_total))}</b></div>
        {d.rev ? <div className="r-row" data-testid="r-rev"><span>{B('نسخة معدّلة رقم', 'Revised copy no.')}</span><b>{d.rev}</b></div> : null}
        {d.payments.map((p, i) => <div className="r-row" key={i}><span>{p.method}</span><span>{fmt(Math.abs(p.amount))}</span>{p.ref ? <span> #{p.ref}</span> : null}</div>)}
        {d.gift_card ? <div className="r-row" data-testid="r-gift"><span>{B('رصيد كارت الهدية', 'Gift card balance')} {d.gift_card}</span><span>{fmt(d.gift_balance)}</span></div> : null}
        {d.exchange_credit_used ? <div className="r-row"><span>{B('رصيد استبدال مستخدم', 'Exchange credit used')} {d.exchange_credit_used.name}</span><span>{fmt(d.exchange_credit_used.amount)}</span></div> : null}
        {ex ? (
          <div className="r-box" data-testid="r-exchange">
            <div className="r-center r-sub">{B('إشعار استبدال', 'Exchange Receipt')}</div>
            <div className="r-center"><Barcode value={ex.name} /></div>
            <div className="r-row"><span>{B('القيمة', 'Value')}</span><b>{fmt(ex.amount)}</b></div>
            {ex.expires_on ? <div className="r-row" data-testid="r-valid"><span>{B('صالح حتى', 'Valid until')}</span><b>{ex.expires_on}</b></div> : null}
            {d.window_days ? <div className="r-small" data-testid="r-window">{`قابل للاستبدال خلال ${d.window_days} يوم من تاريخ الإصدار / Redeemable within ${d.window_days} days of issue`}</div> : null}
          </div>) : null}
        {d.terms_ar || d.terms_en ? (
          <div className="r-terms" data-testid="r-terms">
            {d.terms_ar ? <div dir="rtl">{d.terms_ar}</div> : null}
            {d.terms_en ? <div dir="ltr">{d.terms_en}</div> : null}
          </div>) : null}
        <div className="r-center r-small">{B('شكراً لتسوقكم معنا', 'Thank you for shopping with us')}</div>
      </div>
    </div>
  );
}
