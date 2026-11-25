
(function () {
  var KEY = "smartlab-theme", root = document.documentElement;
  function saved() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function apply(t) {
    root.setAttribute("data-theme", t);
    var b = document.getElementById("theme-toggle");
    if (b) b.textContent = t === "dark" ? "\u2600 Light mode" : "\u263E Dark mode";
  }
  apply(saved() === "light" ? "light" : "dark");
  document.addEventListener("DOMContentLoaded", function () {
    apply(root.getAttribute("data-theme"));
    var b = document.getElementById("theme-toggle");
    if (b) b.addEventListener("click", function () {
      var t = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      try { localStorage.setItem(KEY, t); } catch (e) {}
      apply(t);
    });
  });
})();
