/* Emojis that wiggle about in the page background, behind the glass panels.
 * They are decoration only: they never take taps, and html[data-fun="off"] (Settings) hides them.
 * Each one has its own spot (--x/--y), size (--s), speed (--t) and head start (--d).
 * On devices with a mouse, they also shy away from the pointer. */
(function () {
  "use strict";

  // [emoji, left %, top %, size (rem), seconds per wiggle, head start (s)]
  var SPOTS = [
    ["🌱", 6, 12, 3.0, 9, -1],
    ["🍃", 86, 9, 3.4, 11, -4],
    ["⭐", 44, 5, 2.2, 8, -6],
    ["🌸", 92, 44, 2.6, 10, -2],
    ["🍀", 3, 52, 2.4, 12, -7],
    ["🌿", 21, 84, 3.2, 9.5, -3],
    ["💡", 64, 88, 2.8, 10.5, -5],
    ["🦋", 90, 82, 3.0, 8.5, -8],
    ["✨", 34, 30, 2.0, 13, -9],
    ["📚", 74, 26, 2.1, 11.5, -2.5],
    ["💚", 55, 62, 2.2, 12.5, -6.5],
    ["🌈", 12, 30, 2.0, 10, -10]
  ];
  var reduced = matchMedia("(prefers-reduced-motion: reduce)");
  var canHover = matchMedia("(hover: hover) and (pointer: fine)");
  var RADIUS = 190;   // how close the pointer has to get
  var PUSH = 70;      // the furthest an emoji gets nudged, in px
  var pointer = null, queued = false, items = [];

  function fill(box) {
    box.replaceChildren();
    if (document.documentElement.dataset.fun === "off") return;
    SPOTS.forEach(function (s) {
      var outer = document.createElement("span");
      outer.className = "emo-bit";
      outer.style.cssText = "--x:" + s[1] + "%;--y:" + s[2] + "%;--s:" + s[3] + "rem;--t:" + s[4] + "s;--d:" + s[5] + "s";
      var inner = document.createElement("span");
      inner.textContent = s[0];
      outer.appendChild(inner);
      box.appendChild(outer);
    });
  }

  function paint() {
    queued = false;
    items.forEach(function (item) {
      var px = 0, py = 0;
      if (pointer) {
        // offsetLeft/Top ignore transforms, so the nudge can't feed back into itself
        var dx = item.offsetLeft + item.offsetWidth / 2 - pointer.x;
        var dy = item.offsetTop + item.offsetHeight / 2 - pointer.y;
        var dist = Math.sqrt(dx * dx + dy * dy) || 1;
        if (dist < RADIUS) {
          var force = (1 - dist / RADIUS) * PUSH;
          px = (dx / dist) * force; py = (dy / dist) * force;
        }
      }
      item.style.setProperty("--px", px.toFixed(1) + "px");
      item.style.setProperty("--py", py.toFixed(1) + "px");
    });
  }
  function queue() { if (!queued) { queued = true; requestAnimationFrame(paint); } }

  function refresh() {
    document.querySelectorAll(".emoji-bg").forEach(fill);
    items = Array.prototype.slice.call(document.querySelectorAll(".emoji-bg .emo-bit"));
  }

  window.BobenEmojiBg = { refresh: refresh };
  refresh();

  // Phones have no hovering pointer, so the wiggle alone is enough there.
  if (!reduced.matches && canHover.matches) {
    document.addEventListener("pointermove", function (e) { pointer = { x: e.clientX, y: e.clientY }; queue(); }, { passive: true });
    document.addEventListener("pointerleave", function () { pointer = null; queue(); });
  }
})();
