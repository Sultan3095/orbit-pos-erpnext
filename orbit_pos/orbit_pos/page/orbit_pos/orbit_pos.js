frappe.pages['orbit-pos'].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({ parent: wrapper, title: 'Orbit POS', single_column: true });
  $(page.body).html('<iframe src="/assets/orbit_pos/pos/index.html" style="width:100%;height:calc(100vh - 120px);border:0"></iframe>');
};
