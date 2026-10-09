// Anonymous visit counter for the private stats page (cgi-bin/stats.py).
// Sends: page path, referrer and the browser time zone (used for the country).
// No cookies are set and the server never stores IP addresses.
// Your own browser: open any page with ?notrack to stop counting it, ?track to count it again.
(function () {
  var KEY = 'opumni-notrack';
  try {
    if (/[?&]notrack\b/.test(location.search)) localStorage.setItem(KEY, '1');
    if (/[?&]track\b/.test(location.search)) localStorage.removeItem(KEY);
    if (localStorage.getItem(KEY)) return;
  } catch (e) { /* storage blocked: keep counting */ }
  if (!navigator.sendBeacon || navigator.webdriver) return;

  // Works both on the server (/~opumni/...) and in local preview (/...).
  var base = location.pathname.indexOf('/~opumni/') === 0 ? '/~opumni/' : '/';
  var endpoint = base + 'cgi-bin/hit.py';
  var page = '/' + location.pathname.slice(base.length);
  var tz = '';
  try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) {}

  function send(data) {
    try { navigator.sendBeacon(endpoint, JSON.stringify(data)); } catch (e) {}
  }

  send({ k: 'view', p: page, r: document.referrer, tz: tz });

  // Count CV / paper PDF downloads and clicks to other sites.
  document.addEventListener('click', function (e) {
    var a = e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || a.protocol.indexOf('http') !== 0) return;
    if (a.host !== location.host || /\.pdf$/i.test(a.pathname)) {
      send({ k: 'click', p: page, t: a.href, tz: tz });
    }
  });
})();
