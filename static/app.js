const state = { departments: [], employees: [], schedules: [], shifts: [], filter: "all", department: "all" };
const palette = ["#dceaff", "#ffeddd", "#eee8ff", "#ddf4ec", "#ffe4eb", "#e7eef8"];
const initials = (name) => name.split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase();
const dateLabel = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
const el = (id) => document.getElementById(id);
let toastTimer;

async function api(url, options = {}) {
  const response = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function notify(message, error = false) {
  const toast = el("toast");
  toast.textContent = message;
  toast.classList.toggle("error", error);
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2800);
}

async function loadData() {
  Object.assign(state, await api("/api/data"));
  render();
}

function render() {
  renderFilters();
  renderMetrics();
  renderShifts();
  renderDepartments();
  renderEmployees();
  const schedule = state.schedules[0];
  if (schedule) {
    const start = new Date(`${schedule.start_date}T12:00:00`);
    const end = new Date(`${schedule.end_date}T12:00:00`);
    el("week-label").innerHTML = `<span>▦</span> ${start.toLocaleDateString("en-US", { month: "short", day: "numeric" })} – ${end.toLocaleDateString("en-US", { month: "short", day: "numeric" })} <span class="chevron">⌄</span>`;
  }
}

function renderFilters() {
  const current = el("department-filter").value || "all";
  el("department-filter").innerHTML = `<option value="all">All departments</option>${state.departments.map((dept) => `<option value="${dept.id}">${dept.name}</option>`).join("")}`;
  el("department-filter").value = state.departments.some((dept) => String(dept.id) === current) ? current : "all";
  for (const id of ["employee-department", "shift-department"]) {
    el(id).innerHTML = state.departments.map((dept) => `<option value="${dept.id}">${dept.name}</option>`).join("");
  }
  el("shift-schedule").innerHTML = state.schedules.map((schedule) => `<option value="${schedule.id}">${schedule.name}</option>`).join("");
}

function renderMetrics() {
  const required = state.shifts.reduce((sum, shift) => sum + shift.required_staff, 0);
  const assigned = state.shifts.reduce((sum, shift) => sum + shift.assigned_count, 0);
  const open = Math.max(required - assigned, 0);
  const filled = state.shifts.filter((shift) => shift.assigned_count >= shift.required_staff).length;
  const percent = required ? Math.round((assigned / required) * 100) : 0;
  el("metric-team").textContent = state.employees.filter((employee) => employee.active).length;
  el("metric-shifts").textContent = state.shifts.length;
  el("metric-filled").textContent = `${filled} of ${state.shifts.length}`;
  el("metric-coverage").textContent = percent;
  el("coverage-bar").style.width = `${percent}%`;
  el("metric-open").textContent = open;
  el("open-count").textContent = open;
  el("all-count").textContent = state.shifts.length;
  el("nav-open-count").textContent = open;
}

function renderShifts() {
  const visible = state.shifts.filter((shift) => {
    const needsStaff = shift.assigned_count < shift.required_staff;
    return (state.filter !== "open" || needsStaff) &&
      (state.department === "all" || String(shift.department_id) === state.department);
  });
  el("shift-rows").innerHTML = visible.map((shift) => {
    const assigned = (shift.assigned_names || "").split(", ").filter(Boolean);
    const avatars = assigned.map((name, index) => `<span class="avatar" title="${name}" style="background:${palette[(index + shift.id) % palette.length]};color:#465a76">${initials(name)}</span>`).join("");
    const placeholders = Array.from({ length: Math.max(shift.required_staff - assigned.length, 0) }, () => `<span class="avatar unassigned">＋</span>`).join("");
    const eligible = state.employees.filter((person) => person.department_id === shift.department_id);
    const options = eligible.map((person) => `<option value="${person.id}">${person.name}</option>`).join("");
    return `<tr><td class="shift-name">${shift.label}</td><td><span class="dept-pill"><i style="background:${shift.department_color}"></i>${shift.department}</span></td><td class="shift-date">${dateLabel(shift.shift_date)}<span class="shift-time">${shift.start_time} – ${shift.end_time}</span></td><td><div class="team-avatars">${avatars}${placeholders}</div></td><td><span class="status ${shift.assigned_count >= shift.required_staff ? "covered" : "open"}">${shift.assigned_count >= shift.required_staff ? "Covered" : "Needs staff"}</span></td><td>${shift.assigned_count < shift.required_staff ? `<select class="assign-select" data-shift="${shift.id}"><option value="">＋ Assign</option>${options}</select>` : ""}</td></tr>`;
  }).join("");
  el("empty-shifts").hidden = visible.length > 0;
  el("table-summary").textContent = `Showing ${visible.length} of ${state.shifts.length} shifts`;
  document.querySelectorAll(".assign-select").forEach((select) => select.addEventListener("change", async (event) => {
    if (!event.target.value) return;
    try {
      await api("/api/assignments", { method: "POST", body: JSON.stringify({ shift_id: event.target.dataset.shift, employee_id: event.target.value }) });
      notify("Employee assigned to shift.");
      await loadData();
    } catch (error) {
      notify(error.message, true);
      event.target.value = "";
    }
  }));
}

function renderDepartments() {
  el("department-list").innerHTML = state.departments.map((dept, index) => {
    const people = state.employees.filter((employee) => employee.department_id === dept.id && employee.active);
    return `<div class="department-row"><span class="department-symbol" style="background:${palette[index % palette.length]};color:${dept.color}">${["⌂", "♨", "◈", "✦"][index % 4]}</span><div><span class="department-name">${dept.name}</span><span class="department-sub">${people.length} team ${people.length === 1 ? "member" : "members"}</span></div><span class="department-count">${String(people.length).padStart(2, "0")}</span></div>`;
  }).join("");
}

function renderEmployees() {
  el("team-count-label").textContent = `(${state.employees.length})`;
  el("employee-grid").innerHTML = state.employees.map((person, index) => {
    const days = person.availability.length;
    const start = person.availability.reduce((time, slot) => slot.start_time < time ? slot.start_time : time, "23:59");
    const end = person.availability.reduce((time, slot) => slot.end_time > time ? slot.end_time : time, "00:00");
    return `<article class="employee-card"><span class="avatar" style="background:${palette[index % palette.length]};color:${person.department_color}">${initials(person.name)}</span><div><strong>${person.name}</strong><small>${person.role} · ${person.department}</small><small>${days} available days · ${days ? `${start}–${end}` : "No availability set"}</small></div><i class="employee-dept-dot" style="background:${person.department_color}"></i></article>`;
  }).join("");
}

function openDialog(id) {
  const dialog = el(id);
  dialog.showModal();
  const error = dialog.querySelector(".form-error");
  if (error) error.textContent = "";
}

document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
el("add-employee-open").addEventListener("click", () => openDialog("employee-dialog"));
el("team-add-button").addEventListener("click", () => openDialog("employee-dialog"));
el("add-shift-open").addEventListener("click", () => {
  const schedule = state.schedules[0];
  if (schedule) el("shift-date").min = schedule.start_date, el("shift-date").max = schedule.end_date, el("shift-date").value = schedule.start_date;
  openDialog("shift-dialog");
});
el("department-filter").addEventListener("change", (event) => { state.department = event.target.value; renderShifts(); });
document.querySelectorAll(".filter-tab").forEach((button) => button.addEventListener("click", () => {
  state.filter = button.dataset.filter;
  document.querySelectorAll(".filter-tab").forEach((tab) => tab.classList.toggle("active", tab === button));
  renderShifts();
}));
el("week-label").addEventListener("click", () => {
  el("schedule").scrollIntoView({ behavior: "smooth", block: "start" });
});
document.querySelector(".icon-button").addEventListener("click", () => {
  const openCount = state.shifts.reduce((sum, shift) => sum + Math.max(shift.required_staff - shift.assigned_count, 0), 0);
  if (!openCount) {
    notify("All shifts are fully staffed.");
    return;
  }
  state.filter = "open";
  state.department = "all";
  el("department-filter").value = "all";
  document.querySelectorAll(".filter-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.filter === "open"));
  renderShifts();
  el("schedule").scrollIntoView({ behavior: "smooth", block: "start" });
  notify(`${openCount} shift ${openCount === 1 ? "spot needs" : "spots need"} coverage.`);
});
document.querySelectorAll(".nav-link").forEach((link) => link.addEventListener("click", () => {
  document.querySelectorAll(".nav-link").forEach((item) => item.classList.toggle("active", item === link));
}));
document.querySelectorAll('a[href="#schedule"]').forEach((link) => link.addEventListener("click", () => {
  state.filter = "all";
  document.querySelectorAll(".filter-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.filter === "all"));
  renderShifts();
}));

el("employee-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  const body = Object.fromEntries(formData.entries());
  body.weekdays = formData.getAll("weekdays").map(Number);
  try {
    await api("/api/employees", { method: "POST", body: JSON.stringify(body) });
    form.reset();
    el("employee-dialog").close();
    notify("Team member added.");
    await loadData();
  } catch (error) { el("employee-error").textContent = error.message; }
});

el("shift-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const body = Object.fromEntries(new FormData(form).entries());
  try {
    await api("/api/shifts", { method: "POST", body: JSON.stringify(body) });
    form.reset();
    el("shift-dialog").close();
    notify("Shift added to the schedule.");
    await loadData();
  } catch (error) { el("shift-error").textContent = error.message; }
});

async function autoAssign() {
  try {
    const result = await api("/api/auto-assign", { method: "POST", body: "{}" });
    notify(result.unfilled ? `Assigned ${result.assigned} people; ${result.unfilled} spots still need cover.` : `Great! ${result.assigned} assignments made and all shifts are covered.`);
    await loadData();
  } catch (error) { notify(error.message, true); }
}
el("auto-assign").addEventListener("click", autoAssign);
el("tip-auto-assign").addEventListener("click", autoAssign);
loadData().catch((error) => notify(`Could not load workspace: ${error.message}`, true));
