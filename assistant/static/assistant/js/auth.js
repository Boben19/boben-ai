/* Small helpers for the sign-in, sign-up and profile pages. */
(function () {
  "use strict";

  // Show / hide password
  document.querySelectorAll("[data-toggle-pw]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.dataset.togglePw);
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.textContent = show ? "Hide" : "Show";
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
  });

  // Loading state on forms (the server still validates everything)
  document.querySelectorAll("[data-auth-form]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var btn = form.querySelector(".submit-btn");
      if (btn) { btn.classList.add("is-loading"); btn.setAttribute("aria-busy", "true"); }
    });
  });
  // Loading state on OAuth buttons
  document.querySelectorAll("[data-loading-link]").forEach(function (a) {
    a.addEventListener("click", function () { a.classList.add("is-loading"); });
  });
  // Coming back with the browser's back button must not leave a spinner stuck
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    document.querySelectorAll(".is-loading").forEach(function (el) { el.classList.remove("is-loading"); });
  });

  // Character counters
  document.querySelectorAll("[data-count-for]").forEach(function (out) {
    var field = document.getElementById(out.dataset.countFor);
    if (!field) return;
    var update = function () { out.textContent = field.value.length; };
    field.addEventListener("input", update); update();
  });

  // Master personalization switch greys out the individual switches
  var master = document.getElementById("id_personalize"), list = document.getElementById("switchList");
  if (master && list) {
    var sync = function () {
      list.classList.toggle("is-off", !master.checked);
      list.querySelectorAll("input").forEach(function (i) { i.disabled = !master.checked; });
    };
    master.addEventListener("change", sync); sync();
    // Disabled checkboxes are not sent. Keep their saved state by sending them again when the form is submitted.
    master.form.addEventListener("submit", function () { list.querySelectorAll("input").forEach(function (i) { i.disabled = false; }); });
  }

  // Preview a newly chosen picture
  var file = document.getElementById("id_avatar"), prev = document.getElementById("avatarPreview");
  if (file && prev) {
    file.addEventListener("change", function () {
      var f = file.files && file.files[0];
      if (!f || !/^image\//.test(f.type)) return;
      var img = prev.querySelector("img") || document.createElement("img");
      img.alt = "Your new profile picture";
      img.src = URL.createObjectURL(f);
      prev.replaceChildren(img);
    });
  }

  // Signing out: first forget the saved copy of the chat page (the offline cache), so the next
  // person on this device never sees it, then send the sign-out request.
  document.querySelectorAll("[data-logout]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (form.dataset.cleared || !window.caches) return;
      e.preventDefault();
      var go = function () { form.dataset.cleared = "1"; form.submit(); };
      caches.keys()
        .then(function (keys) { return Promise.all(keys.filter(function (k) { return k.indexOf("boben") === 0; }).map(function (k) { return caches.delete(k); })); })
        .then(go, go);
    });
  });
})();
