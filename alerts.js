/* Live alerts on every page: one Server-Sent Events connection -> navbar badge + toast. */
(function () {
  if (!window.EventSource) return;
  var badge = document.getElementById("alert-badge");
  var box = document.createElement("div");
  box.className = "toast-box";
  document.body.appendChild(box);
  var tones = { Critical: "danger", Warning: "warning", Info: "info" };

  function toast(a) {
    var t = document.createElement("div");
    t.className = "toast";
    t.setAttribute("data-tone", tones[a.severity] || "info");
    var h = document.createElement("strong");
    h.textContent = a.severity + " \u00B7 " + a.computer_id;
    t.appendChild(h);
    t.appendChild(document.createTextNode(a.message));
    t.addEventListener("click", function () { location.href = "/fleet"; });
    box.appendChild(t);
    setTimeout(function () { t.remove(); }, 8000);
  }

  var es = new EventSource("/fleet/stream");
  es.addEventListener("alert", function (e) {
    var a = JSON.parse(e.data);
    toast(a);
    document.dispatchEvent(new CustomEvent("smartlab:alert", { detail: a }));
  });
  es.addEventListener("count", function (e) {
    var n = parseInt(e.data, 10);
    if (badge) { badge.textContent = n; badge.hidden = n === 0; }
    document.dispatchEvent(new CustomEvent("smartlab:count", { detail: n }));
  });
})();
