"""Custom HTML Block — "Accounts Team Reminders".

Renders the manager's plain-text reminders as a designed board on the
Accounts workspace: open reminder cards (overdue / due today / upcoming
colouring), one-click Done, and a recently-completed strip. Runs inside a
shadow DOM (see frappe.dom.create_shadow_element); the script receives
``root_element`` (the shadowRoot) and styles are scoped to it.
"""

import frappe

REMINDER_BLOCK_NAME = "Accounts Team Reminders"

REMINDER_BLOCK_HTML = """
<div class="ar-board">
	<div class="ar-head">
		<div class="ar-title">Team Reminders</div>
		<div class="ar-count" id="ar-count"></div>
		<div class="ar-actions">
			<button class="ar-btn" id="ar-refresh" title="Refresh">&#8635; Refresh</button>
			<button class="ar-btn primary" id="ar-new">+ New Reminder</button>
		</div>
	</div>
	<div class="ar-grid" id="ar-open"></div>
	<div class="ar-empty" id="ar-empty" style="display:none">No open reminders. Everything is done.</div>
	<div class="ar-done-wrap" id="ar-done-wrap" style="display:none">
		<div class="ar-sub">Recently completed</div>
		<div id="ar-done"></div>
	</div>
</div>
"""

REMINDER_BLOCK_STYLE = """
.ar-board { font-size: 13px; color: #202124; }
.ar-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.ar-title { font-size: 16px; font-weight: 600; }
.ar-count { background: #eef1f6; border-radius: 999px; padding: 2px 10px; font-size: 12px; color: #5f6368; }
.ar-actions { margin-left: auto; display: flex; gap: 8px; }
.ar-btn { border: 1px solid #dadce0; background: #fff; color: #3c4043; border-radius: 6px;
	padding: 5px 12px; font-size: 12px; cursor: pointer; }
.ar-btn:hover { background: #f5f6f8; }
.ar-btn.primary { background: #3b6ea5; border-color: #3b6ea5; color: #fff; }
.ar-btn.primary:hover { background: #325a86; }
.ar-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
.ar-card { background: #fff; border: 1px solid #e4e7ec; border-left-width: 4px; border-radius: 8px;
	padding: 12px 14px; display: flex; flex-direction: column; gap: 10px;
	box-shadow: 0 1px 2px rgba(60,64,67,.06); transition: box-shadow .15s; }
.ar-card:hover { box-shadow: 0 2px 8px rgba(60,64,67,.14); }
.ar-card.overdue { border-left-color: #d93025; }
.ar-card.today { border-left-color: #f9ab00; }
.ar-card.upcoming { border-left-color: #3b6ea5; }
.ar-card.nodate { border-left-color: #9aa0a6; }
.ar-text { line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
.ar-foot { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ar-badge { font-size: 11px; border-radius: 4px; padding: 2px 7px; font-weight: 500; }
.ar-badge.overdue { background: #fce8e6; color: #c5221f; }
.ar-badge.today { background: #fef7e0; color: #b06000; }
.ar-badge.upcoming { background: #e8f0fe; color: #1a73e8; }
.ar-badge.nodate { background: #f1f3f4; color: #5f6368; }
.ar-badge.done { background: #e6f4ea; color: #137333; }
.ar-by { font-size: 11px; color: #80868b; }
.ar-done-btn { margin-left: auto; border: 1px solid #dadce0; background: #fff; color: #137333;
	border-radius: 6px; padding: 3px 10px; font-size: 12px; cursor: pointer; }
.ar-done-btn:hover { background: #e6f4ea; }
.ar-empty { border: 1px dashed #dadce0; border-radius: 8px; padding: 22px; text-align: center; color: #5f6368; }
.ar-sub { font-size: 12px; font-weight: 600; color: #5f6368; text-transform: uppercase; letter-spacing: .4px; margin: 16px 0 8px; }
.ar-done-item { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-bottom: 1px solid #f1f3f4; }
.ar-done-item .ar-text { text-decoration: line-through; color: #80868b; flex: 1; }
.ar-check { color: #137333; font-weight: 700; }
.ar-load { color: #5f6368; padding: 10px 0; }
"""

REMINDER_BLOCK_SCRIPT = """
(function () {
	let root = root_element;
	let $ = (sel) => root.querySelector(sel);
	let API = "boq_budget_control.boq_budget.api";

	function badge(status, due) {
		let labels = { overdue: "Overdue", today: "Due today", upcoming: "Due", nodate: "No due date" };
		let b = document.createElement("span");
		b.className = "ar-badge " + status;
		b.textContent = status === "upcoming" || status === "overdue" ? (labels[status] + (due ? " " + due : "")) : labels[status];
		return b;
	}

	function card(item) {
		let c = document.createElement("div");
		c.className = "ar-card " + item.status;
		let text = document.createElement("div");
		text.className = "ar-text";
		text.textContent = item.reminder_text;
		let foot = document.createElement("div");
		foot.className = "ar-foot";
		foot.appendChild(badge(item.status, item.due_date_display));
		let by = document.createElement("span");
		by.className = "ar-by";
		by.textContent = "by " + (item.owner_name || item.owner);
		foot.appendChild(by);
		let btn = document.createElement("button");
		btn.className = "ar-done-btn";
		btn.textContent = "Done";
		btn.onclick = () => toggle(item.name, btn);
		foot.appendChild(btn);
		c.appendChild(text);
		c.appendChild(foot);
		return c;
	}

	function toggle(name, btn) {
		btn.disabled = true;
		frappe.xcall(API + ".toggle_reminder_done", { name: name, done: 1 }).then(load).catch(() => { btn.disabled = false; });
	}

	function render(data) {
		let open = $("#ar-open"), empty = $("#ar-empty"), doneWrap = $("#ar-done-wrap"), doneBox = $("#ar-done"), count = $("#ar-count");
		open.innerHTML = "";
		data.open.forEach((item) => open.appendChild(card(item)));
		empty.style.display = data.open.length ? "none" : "block";
		count.textContent = data.open.length + " open";
		doneBox.innerHTML = "";
		data.completed.forEach((item) => {
			let row = document.createElement("div");
			row.className = "ar-done-item";
			let check = document.createElement("span");
			check.className = "ar-check";
			check.textContent = "✓";
			let text = document.createElement("span");
			text.className = "ar-text";
			text.textContent = item.reminder_text;
			row.appendChild(check);
			row.appendChild(text);
			doneBox.appendChild(row);
		});
		doneWrap.style.display = data.completed.length ? "block" : "none";
	}

	function load() {
		let open = $("#ar-open");
		open.innerHTML = '<div class="ar-load">Loading reminders…</div>';
		frappe.xcall(API + ".get_accounts_reminders").then(render).catch((e) => {
			open.innerHTML = "";
			frappe.msgprint({ message: "Could not load reminders: " + (e && e.message ? e.message : e), indicator: "red", title: "Accounts Reminders" });
		});
	}

	$("#ar-refresh").onclick = load;
	$("#ar-new").style.display = ["Accounts Manager", "Accounting Manager", "System Manager"].some((r) => frappe.user_roles.includes(r)) ? "" : "none";
	$("#ar-new").onclick = () => frappe.new_doc("Accounts Reminder");
	load();
})();
"""

ROLES = ("Accounts Manager", "Accounting Manager", "Accounts User", "System Manager")


def make_custom_block():
	"""Create or update the Accounts Team Reminders custom block (idempotent)."""
	exists = frappe.db.exists("Custom HTML Block", REMINDER_BLOCK_NAME)
	if exists:
		block = frappe.get_doc("Custom HTML Block", REMINDER_BLOCK_NAME)
	else:
		block = frappe.get_doc({"doctype": "Custom HTML Block", "__newname": REMINDER_BLOCK_NAME})

	block.html = REMINDER_BLOCK_HTML
	block.script = REMINDER_BLOCK_SCRIPT
	block.style = REMINDER_BLOCK_STYLE
	block.set("roles", [])
	for role in ROLES:
		block.append("roles", {"role": role})

	if exists:
		block.save(ignore_permissions=True)
	else:
		block.insert(ignore_permissions=True)
