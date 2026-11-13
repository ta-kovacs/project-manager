// The screens: sign in / create an account, the project list, and one project.
// Routes live in the URL hash: #/ (projects) and #/projects/<id>.

import * as api from "./api.js";

const app = document.getElementById("app");
const flash = document.getElementById("flash");
const userBar = document.getElementById("user-bar");

// --- helpers ---

// Build an element. Strings become text nodes (never HTML), so user content can't inject markup.
function h(tag, attributes = {}, ...children) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === false || value === null || value === undefined) continue;
    if (name.startsWith("on")) element.addEventListener(name.slice(2), value);
    else if (name === "class") element.className = value;
    else element.setAttribute(name, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return element;
}

let messageShownAt = 0;

function showMessage(text, kind = "info") {
  messageShownAt = Date.now();
  flash.replaceChildren(h("p", { class: `message ${kind}`, role: kind === "error" ? "alert" : "status" }, text));
}

function clearMessage() {
  flash.replaceChildren();
}

// Run an action, showing its error (if any) instead of failing silently.
async function attempt(action) {
  try {
    return await action();
  } catch (error) {
    showMessage(error.message || String(error), "error");
    return undefined;
  }
}

function formatSize(bytes) {
  if (bytes === null || bytes === undefined) return "unknown size";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function field(label, input) {
  return h("label", { class: "field" }, h("span", {}, label), input);
}

function navigate(hash) {
  if (location.hash === hash) render();
  else location.hash = hash;
}

// --- sign in / create an account ---

function authView() {
  const logInForm = h(
    "form",
    {
      class: "card",
      onsubmit: (event) => {
        event.preventDefault();
        const data = new FormData(event.target);
        attempt(async () => {
          await api.logIn(data.get("username"), data.get("password"));
          clearMessage();
          navigate("#/");
        });
      },
    },
    h("h2", {}, "Log in"),
    field("Username", h("input", { name: "username", required: true, autocomplete: "username" })),
    field(
      "Password",
      h("input", { name: "password", type: "password", required: true, autocomplete: "current-password" }),
    ),
    h("button", { type: "submit" }, "Log in"),
  );

  const registerForm = h(
    "form",
    {
      class: "card",
      onsubmit: (event) => {
        event.preventDefault();
        const data = new FormData(event.target);
        attempt(async () => {
          await api.register(data.get("username"), data.get("password"), data.get("repeat"));
          await api.logIn(data.get("username"), data.get("password"));
          showMessage("Account created. Welcome!", "success");
          navigate("#/");
        });
      },
    },
    h("h2", {}, "Create an account"),
    field("Username", h("input", { name: "username", required: true, minlength: 3, autocomplete: "username" })),
    field(
      "Password",
      h("input", {
        name: "password",
        type: "password",
        required: true,
        minlength: 10,
        maxlength: 128,
        autocomplete: "new-password",
        "aria-describedby": "password-rules",
      }),
    ),
    // The API is the source of truth for these rules (app/schemas/user_schema.py); keep the text in step.
    h(
      "p",
      { id: "password-rules", class: "small" },
      "At least 10 characters, with a lowercase letter, an uppercase letter and a digit, and not containing your username.",
    ),
    field(
      "Repeat password",
      h("input", { name: "repeat", type: "password", required: true, minlength: 10, autocomplete: "new-password" }),
    ),
    h("button", { type: "submit" }, "Create account"),
  );

  return h("div", { class: "columns" }, logInForm, registerForm);
}

// --- project list ---

async function projectsView() {
  const projects = await api.listProjects();
  const username = api.session.get().username;

  const list = projects.length
    ? h(
        "ul",
        { class: "project-list" },
        projects.map((project) =>
          h(
            "li",
            {},
            h(
              "a",
              { class: "card project-card", href: `#/projects/${project.id}` },
              h("strong", {}, project.name),
              project.description ? h("span", { class: "muted" }, project.description) : null,
              h(
                "span",
                { class: "meta" },
                project.owner.username === username ? "Owner: you" : `Owner: ${project.owner.username}`,
                ` · ${project.documents.length} document(s) · ${formatSize(project.storage_used_bytes)}`,
              ),
            ),
          ),
        ),
      )
    : h("p", { class: "muted" }, "No projects yet. Create your first one below.");

  const createForm = h(
    "form",
    {
      class: "card",
      onsubmit: (event) => {
        event.preventDefault();
        const data = new FormData(event.target);
        attempt(async () => {
          const project = await api.createProject(data.get("name").trim(), data.get("description").trim());
          showMessage(`Created “${project.name}”.`, "success");
          navigate(`#/projects/${project.id}`);
        });
      },
    },
    h("h2", {}, "New project"),
    field("Name", h("input", { name: "name", required: true, maxlength: 250 })),
    field("Description", h("textarea", { name: "description", rows: 3, maxlength: 5000 })),
    h("button", { type: "submit" }, "Create project"),
  );

  return h("div", {}, h("h1", {}, "Your projects"), list, createForm);
}

// --- one project ---

async function projectView(id) {
  const project = await api.getProject(id);
  const isOwner = project.owner.username === api.session.get().username;
  const reload = () => render();

  const detailsForm = h(
    "form",
    {
      class: "card",
      onsubmit: (event) => {
        event.preventDefault();
        const data = new FormData(event.target);
        attempt(async () => {
          await api.updateProject(id, data.get("name").trim(), data.get("description").trim());
          showMessage("Details saved.", "success");
          reload();
        });
      },
    },
    h("h2", {}, "Details"),
    field("Name", h("input", { name: "name", required: true, maxlength: 250, value: project.name })),
    field("Description", h("textarea", { name: "description", rows: 3, maxlength: 5000 }, project.description || "")),
    h("button", { type: "submit" }, "Save"),
  );

  const documentRows = project.documents.map((document_) =>
    h(
      "tr",
      {},
      h("td", {}, document_.original_filename),
      h("td", { class: "muted" }, formatSize(document_.size_bytes)),
      h(
        "td",
        { class: "actions" },
        h(
          "button",
          {
            type: "button",
            class: "secondary",
            onclick: () =>
              attempt(async () => {
                const blob = await api.downloadDocument(document_.id);
                const link = h("a", { href: URL.createObjectURL(blob), download: document_.original_filename });
                document.body.append(link);
                link.click();
                link.remove();
                setTimeout(() => URL.revokeObjectURL(link.href), 1000);
              }),
          },
          "Download",
        ),
        isOwner
          ? h(
              "button",
              {
                type: "button",
                class: "danger",
                onclick: () => {
                  if (!confirm(`Delete “${document_.original_filename}”?`)) return;
                  attempt(async () => {
                    await api.deleteDocument(document_.id);
                    showMessage("Document deleted.", "success");
                    reload();
                  });
                },
              },
              "Delete",
            )
          : null,
      ),
    ),
  );

  const documents = h(
    "section",
    { class: "card" },
    h("h2", {}, "Documents"),
    project.documents.length
      ? h("table", {}, h("tbody", {}, documentRows))
      : h("p", { class: "muted" }, "No documents yet."),
    h(
      "form",
      {
        class: "inline",
        onsubmit: (event) => {
          event.preventDefault();
          const files = event.target.elements.files.files;
          if (!files.length) return;
          attempt(async () => {
            const created = await api.uploadDocuments(id, files);
            showMessage(`Uploaded ${created.length} document(s).`, "success");
            reload();
          });
        },
      },
      h("input", { name: "files", type: "file", multiple: true, accept: ".pdf,.docx", required: true }),
      h("button", { type: "submit" }, "Upload"),
    ),
    h("p", { class: "muted small" }, "PDF or DOCX files.", ` Storage used: ${formatSize(project.storage_used_bytes)}.`),
  );

  const ownerTools = isOwner
    ? [
        h(
          "section",
          { class: "card" },
          h("h2", {}, "Share"),
          h(
            "form",
            {
              class: "inline",
              onsubmit: (event) => {
                event.preventDefault();
                const username = new FormData(event.target).get("username").trim();
                attempt(async () => {
                  await api.inviteUser(id, username);
                  showMessage(`${username} can now access this project.`, "success");
                  event.target.reset();
                });
              },
            },
            h("input", { name: "username", required: true, placeholder: "Username", "aria-label": "Username" }),
            h("button", { type: "submit" }, "Invite user"),
          ),
          h(
            "form",
            {
              class: "inline",
              onsubmit: (event) => {
                event.preventDefault();
                const email = new FormData(event.target).get("email").trim();
                attempt(async () => {
                  await api.shareProject(id, email);
                  showMessage(`A join link was sent to ${email}.`, "success");
                  event.target.reset();
                });
              },
            },
            h("input", { name: "email", type: "email", required: true, placeholder: "Email", "aria-label": "Email" }),
            h("button", { type: "submit" }, "Email a join link"),
          ),
        ),
        h(
          "section",
          { class: "card danger-zone" },
          h("h2", {}, "Delete project"),
          h("p", { class: "muted" }, "Deletes the project and all of its documents. This can't be undone."),
          h(
            "button",
            {
              type: "button",
              class: "danger",
              onclick: () => {
                if (!confirm(`Delete “${project.name}” and all its documents?`)) return;
                attempt(async () => {
                  await api.deleteProject(id);
                  showMessage("Project deleted.", "success");
                  navigate("#/");
                });
              },
            },
            "Delete project",
          ),
        ),
      ]
    : [];

  return h(
    "div",
    {},
    h("a", { href: "#/", class: "back" }, "← All projects"),
    h("h1", {}, project.name),
    h("p", { class: "muted" }, isOwner ? "You own this project." : `Owner: ${project.owner.username} · you're a participant`),
    detailsForm,
    documents,
    ownerTools,
  );
}

// --- rendering ---

function renderUserBar(current) {
  userBar.replaceChildren(
    ...(current
      ? [
          h("span", { class: "muted" }, `Signed in as ${current.username}`),
          h(
            "button",
            {
              type: "button",
              class: "secondary",
              onclick: () => {
                api.logOut();
                showMessage("Signed out.");
                navigate("#/");
              },
            },
            "Log out",
          ),
        ]
      : []),
  );
}

async function render() {
  const current = api.session.get();
  renderUserBar(current);
  if (!current) {
    app.replaceChildren(authView());
    return;
  }

  const match = location.hash.match(/^#\/projects\/(\d+)$/);
  app.replaceChildren(h("p", { class: "muted" }, "Loading…"));
  try {
    app.replaceChildren(match ? await projectView(Number(match[1])) : await projectsView());
  } catch (error) {
    if (!api.session.get()) return; // the session ended; that handler re-renders
    showMessage(error.message, "error");
    app.replaceChildren(h("a", { href: "#/", class: "back" }, "← All projects"));
  }
}

window.addEventListener("hashchange", () => {
  // Keep a message that led here (e.g. "Created …" before opening the project); drop older ones.
  if (Date.now() - messageShownAt > 1000) clearMessage();
  render();
});
window.addEventListener("session-ended", () => {
  showMessage("Your session has ended. Please log in again.", "error");
  render();
});
render();
