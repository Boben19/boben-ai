/* Soft emojis that drift slowly inside the page background. They sit UNDER the text and
 * never intercept taps. Turn them off with html[data-fun="off"] (the Settings switch does this). */
(function () {
  "use strict";
  var EMOJIS = ["🍀", "🌿", "✨", "💚", "🌸", "☁️", "🦋", "🌈", "⭐", "🍃", "🌱", "📚", "💡"];
  var rnd = function (a, b) { return a + Math.random() * (b - a); };

  function fill(box) {
    box.replaceChildren();
    if (document.documentElement.dataset.fun === "off") return;
    var count = innerWidth < 600 ? 9 : 16;
    for (var i = 0; i < count; i++) {
      var s = document.createElement("span");
      s.className = "emo-bit";
      s.textContent = EMOJIS[Math.floor(Math.random() * EMOJIS.length)];
      s.style.left = rnd(2, 94) + "%";
      s.style.top = rnd(2, 92) + "%";
      s.style.fontSize = rnd(22, 46) + "px";
      s.style.setProperty("--emo-d", rnd(20, 38) + "s");
      s.style.setProperty("--emo-delay", "-" + rnd(0, 20) + "s");
      s.style.setProperty("--emo-x", rnd(-30, 30) + "px");
      s.style.setProperty("--emo-y", rnd(-40, 40) + "px");
      s.style.setProperty("--emo-r0", rnd(-14, 0) + "deg");
      s.style.setProperty("--emo-r1", rnd(0, 14) + "deg");
      box.appendChild(s);
    }
  }
  function refresh() { document.querySelectorAll(".emoji-bg").forEach(fill); }

  window.BobenEmojiBg = { refresh: refresh };
  refresh();
})();
