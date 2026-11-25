export const T = {
  ar: {
    app: 'أوربت POS', shift: 'الشفت', openShift: 'فتح شفت', closeShift: 'إغلاق الشفت', openingCash: 'نقدية الافتتاح',
    countedCash: 'النقدية الفعلية', sell: 'البيع', scan: 'امسح الباركود أو اكتب 3*الباركود', add: 'إضافة',
    qty: 'الكمية', price: 'السعر', total: 'الإجمالي', subtotal: 'المجموع', discount: 'الخصم', pay: 'دفع',
    cash: 'كاش', card: 'كارت', remaining: 'المتبقي', change: 'الباقي', done: 'تمت العملية', empty: 'السلة فاضية',
    online: 'متصل', offline: 'غير متصل', queued: 'عمليات في الانتظار', sync: 'مزامنة', theme: 'المظهر',
    light: 'فاتح', dark: 'داكن', blue: 'أزرق', lang: 'اللغة', noShift: 'افتح شفت الأول', cashIn: 'إدخال نقدية',
    cashOut: 'سحب نقدية', reason: 'السبب', remove: 'حذف', promo: 'عرض', managerPin: 'رقم المدير', expected: 'المتوقع',
    difference: 'الفرق', customerScreen: 'شاشة العميل', thanks: 'شكراً لتسوقكم معنا', notFound: 'الصنف غير موجود',
  },
  en: {
    app: 'Orbit POS', shift: 'Shift', openShift: 'Open shift', closeShift: 'Close shift', openingCash: 'Opening cash',
    countedCash: 'Counted cash', sell: 'Sell', scan: 'Scan barcode or type 3*barcode', add: 'Add',
    qty: 'Qty', price: 'Price', total: 'Total', subtotal: 'Subtotal', discount: 'Discount', pay: 'Pay',
    cash: 'Cash', card: 'Card', remaining: 'Remaining', change: 'Change', done: 'Sale complete', empty: 'Cart is empty',
    online: 'Online', offline: 'Offline', queued: 'Queued sales', sync: 'Sync', theme: 'Theme',
    light: 'Light', dark: 'Dark', blue: 'Blue', lang: 'Language', noShift: 'Open a shift first', cashIn: 'Cash in',
    cashOut: 'Cash out', reason: 'Reason', remove: 'Remove', promo: 'Promo', managerPin: 'Manager PIN', expected: 'Expected',
    difference: 'Difference', customerScreen: 'Customer screen', thanks: 'Thank you for shopping with us', notFound: 'Item not found',
  },
};
export const t = (lang, k) => (T[lang] && T[lang][k]) || T.en[k] || k;
