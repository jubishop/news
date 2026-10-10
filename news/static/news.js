"use strict";

// Photos load from their publishers' hosts; drop any that are gone rather than
// leaving a broken image or an empty frame.
for (const image of document.querySelectorAll("[data-photo] img, .prose img")) {
  const drop = () => (image.closest("[data-photo]") || image).remove();
  image.addEventListener("error", drop);
  // Catches images that failed before this script ran.
  image.decode().catch(() => {
    if (image.complete && !image.naturalWidth) drop();
  });
}

for (const form of document.querySelectorAll("form[data-confirm]")) {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
}

const editor = document.querySelector("[data-schedule-form]");
if (editor) {
  let pending;
  const dateEntries = editor.querySelector("[data-date-entries]");
  const addDate = editor.querySelector("[data-add-date]");

  function numberDates() {
    for (const [index, row] of [...dateEntries.children].entries()) {
      const input = row.querySelector("input");
      const label = row.querySelector("label");
      input.id = `assignment-date-${index + 1}`;
      label.htmlFor = input.id;
      label.textContent = `Assignment date ${index + 1}`;
      row.querySelector("button").setAttribute("aria-label", `Delete assignment date ${index + 1}`);
    }
  }

  addDate?.addEventListener("click", () => {
    dateEntries.append(editor.querySelector("[data-date-template]").content.cloneNode(true));
    numberDates();
    dateEntries.lastElementChild.querySelector("input").focus();
    preview();
  });

  dateEntries.addEventListener("click", (event) => {
    const button = event.target.closest("[data-delete-date]");
    if (!button) return;
    const row = button.closest("[data-date-entry]");
    const next = row.nextElementSibling || row.previousElementSibling;
    row.remove();
    numberDates();
    (next?.querySelector("input") || addDate).focus();
    preview();
  });

  async function preview() {
    const cadence = editor.elements.cadence.value;
    for (const section of editor.querySelectorAll("[data-cadence]")) {
      section.hidden = section.dataset.cadence !== cadence;
      for (const input of section.querySelectorAll("input, select, textarea, button")) {
        input.disabled = section.hidden;
      }
    }
    if (editor.hasAttribute("data-fixed-schedule")) return;
    pending?.abort();
    const dates = new Set();
    for (const input of dateEntries.querySelectorAll("input")) {
      input.setCustomValidity(input.value && dates.has(input.value) ? "Assignment dates must be distinct." : "");
      if (input.value) dates.add(input.value);
    }
    pending = new AbortController();
    const params = new URLSearchParams();
    const fields = new FormData(editor);
    for (const name of ["cadence", "weekdays", "day_of_month", "dates", "reporter_id", "csrf_token"]) {
      for (const value of fields.getAll(name)) params.append(name, value);
    }
    const output = editor.querySelector("[data-schedule-preview]");
    try {
      const response = await fetch("/newsroom/schedule-preview", {
        method: "POST", body: params, signal: pending.signal,
      });
      const data = await response.json();
      output.textContent = response.ok
        ? data.next_date
          ? `First future date for this schedule: ${data.next_date} · Pacific Time. Dates already due stay unchanged.`
          : "No future dates. Unfinished assignments stay due until a successful result."
        : data.message;
    } catch (error) {
      if (error.name !== "AbortError") output.textContent = "New schedules begin tomorrow. Preview is temporarily unavailable.";
    }
  }
  editor.addEventListener("change", (event) => {
    if (["cadence", "weekdays", "day_of_month"].includes(event.target.name)) preview();
  });
  editor.addEventListener("input", (event) => {
    if (event.target.name === "dates") preview();
  });
  preview();
}
