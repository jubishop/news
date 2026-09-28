"use strict";

for (const form of document.querySelectorAll("form[data-confirm]")) {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
}

const editor = document.querySelector("[data-schedule-form]");
if (editor) {
  let pending;
  async function preview() {
    const cadence = editor.elements.cadence.value;
    for (const section of editor.querySelectorAll("[data-cadence]")) {
      section.hidden = section.dataset.cadence !== cadence;
      for (const input of section.querySelectorAll("input, select, textarea")) {
        input.disabled = section.hidden;
      }
    }
    if (editor.hasAttribute("data-fixed-schedule")) return;
    pending?.abort();
    pending = new AbortController();
    const params = new URLSearchParams();
    for (const name of ["cadence", "weekdays", "day_of_month", "dates", "reporter_id", "csrf_token"]) {
      for (const value of new FormData(editor).getAll(name)) params.append(name, value);
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
    if (["cadence", "weekdays", "day_of_month", "dates"].includes(event.target.name)) preview();
  });
  preview();
}
