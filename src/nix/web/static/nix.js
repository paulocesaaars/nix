// Comportamentos pequenos da interface: copiar texto e alternar abas.
(function () {
  "use strict";

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy]");
    if (!button) return;
    var source = document.getElementById(button.getAttribute("data-copy"));
    if (!source) return;
    var label = button.querySelector("[data-label]");
    var original = label ? label.textContent : "";
    var done = function (text) {
      if (!label) return;
      label.textContent = text;
      window.setTimeout(function () { label.textContent = original; }, 1800);
    };
    if (!navigator.clipboard) {
      done("Selecione e copie");
      return;
    }
    navigator.clipboard.writeText(source.textContent).then(
      function () { done("Copiado"); },
      function () { done("Selecione e copie"); }
    );
  });

  document.addEventListener("change", function (event) {
    var box = event.target;
    if (!box || box.id !== "sync-all-vaults") return;
    document.querySelectorAll("[data-all-vaults]").forEach(function (input) {
      input.checked = box.checked;
    });
  });

  document.addEventListener("click", function (event) {
    var tab = event.target.closest("[role='tab']");
    if (!tab) return;
    var list = tab.closest("[role='tablist']");
    if (!list) return;
    list.querySelectorAll("[role='tab']").forEach(function (other) {
      var selected = other === tab;
      other.setAttribute("aria-selected", selected ? "true" : "false");
      var panel = document.getElementById(other.getAttribute("aria-controls"));
      if (panel) panel.hidden = !selected;
    });
  });
})();
