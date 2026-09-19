// Small stroke-icon set shared by the mother app and the clinic dashboard (24x24, currentColor).
// Path data is static and trusted, so innerHTML is safe here; user text never passes through this file.
const ICON_PATHS = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22v-9h6v9"/>',
  sparkles: '<path d="m11 3 2 5.5L18.5 10 13 12l-2 5.5L9 12l-5.5-2L9 8.5z"/><path d="m18.5 15 .9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z"/>',
  message: '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="3"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.100 4.200 2 2 0 0 1 4.100 2h3a2 2 0 0 1 2 1.700c.100 1 .400 1.900.700 2.800a2 2 0 0 1-.500 2.100L8.100 9.900a16 16 0 0 0 6 6l1.300-1.300a2 2 0 0 1 2.100-.400c.900.300 1.800.600 2.800.700a2 2 0 0 1 1.700 2z"/>',
  "alert-triangle": '<path d="M10.300 3.900 1.800 18a2 2 0 0 0 1.700 3h17a2 2 0 0 0 1.700-3L13.700 3.900a2 2 0 0 0-3.400 0z"/><path d="M12 9v4M12 17h.01"/>',
  "alert-octagon": '<path d="M7.900 2h8.200L22 7.900v8.200L16.100 22H7.900L2 16.100V7.900z"/><path d="M12 8v4M12 16h.01"/>',
  "check-circle": '<circle cx="12" cy="12" r="10"/><path d="m8 12.500 2.700 2.700L16 9.500"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  send: '<path d="M22 2 11 13"/><path d="m22 2-7 20-4-9-9-4z"/>',
  "arrow-left": '<path d="M19 12H5M12 19l-7-7 7-7"/>',
  "arrow-right": '<path d="M5 12h14M12 5l7 7-7 7"/>',
  clipboard: '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/><path d="m9 14 2 2 4-4"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.900M16 3.100a4 4 0 0 1 0 7.800"/>',
  heart: '<path d="M20.800 4.600a5.500 5.500 0 0 0-7.800 0L12 5.700l-1.100-1.100a5.500 5.500 0 0 0-7.800 7.800l1.100 1.100L12 21.200l7.800-7.800 1.100-1.100a5.500 5.500 0 0 0 0-7.700z"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  bell: '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.700 21a2 2 0 0 1-3.400 0"/>',
  "bell-off": '<path d="M13.700 21a2 2 0 0 1-3.400 0M18.600 13a17.900 17.900 0 0 1-.600-5 6 6 0 0 0-9.300-5M6.300 6.300A5.900 5.900 0 0 0 6 8c0 7-3 9-3 9h14M2 2l20 20"/>',
  refresh: '<path d="M21 3v6h-6M3 21v-6h6"/><path d="M3.500 9a9 9 0 0 1 14.900-3.400L21 9M3 15l2.600 3.400A9 9 0 0 0 20.500 15"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  flame: '<path d="M12 2c1 3.500 4.500 5.500 4.500 10a4.500 4.500 0 0 1-9 0c0-1.500.500-2.500 1.500-3.500.200 1.500 1 2.500 2 2.500 0-3-1-5 1-9z"/><path d="M8 14a4 4 0 0 0 8 0"/>',
  lightbulb: '<path d="M9 18h6M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.700c.600.500 1 1.300 1 2.300h6c0-1 .400-1.800 1-2.300A7 7 0 0 0 12 2z"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
};

function icon(name, size) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", size || 20);
  svg.setAttribute("height", size || 20);
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("icon");
  svg.innerHTML = ICON_PATHS[name] || "";
  return svg;
}
