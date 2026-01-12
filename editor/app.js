import {
  login,
  getUser,
  isCollaborator,
  loadYaml,
  getMainSha,
  createBranch,
  commitFile,
  openPR
} from "./github.js";

import { parseYaml, dumpYaml } from "./yaml.js";

/* ------------------ STATE ------------------ */

let token = null;
let yamlData = null;
let fileSha = null;
let baseSha = null;

/* ------------------ DOM ------------------ */

const loginBtn = document.getElementById("loginBtn");
const app = document.getElementById("app");
const userInfo = document.getElementById("userInfo");
const tbody = document.querySelector("#mappingsTable tbody");

const addBtn = document.getElementById("addBtn");
const saveBtn = document.getElementById("saveBtn");

const modal = document.getElementById("modal");
const modalCategory = document.getElementById("modalCategory");
const modalDisplayName = document.getElementById("modalDisplayName");
const modalAliases = document.getElementById("modalAliases");
const modalLink = document.getElementById("modalLink");
const modalSave = document.getElementById("modalSave");
const modalCancel = document.getElementById("modalCancel");

/* ------------------ AUTH ------------------ */

loginBtn.onclick = login;

token = new URLSearchParams(window.location.hash.substring(1)).get("access_token");
if (token) init();

/* ------------------ INIT ------------------ */

async function init() {
  const user = await getUser(token);
  userInfo.textContent = user.login;

  const allowed = await isCollaborator(user.login, token);
  if (!allowed) {
    alert("You do not have edit access.");
    return;
  }

  const yamlResult = await loadYaml(token);
  yamlData = parseYaml(yamlResult.content);
  fileSha = yamlResult.sha;
  baseSha = await getMainSha(token);

  app.hidden = false;
  renderTable();
}

/* ------------------ RENDER ------------------ */

function renderTable() {
  tbody.innerHTML = "";

  Object.entries(yamlData).forEach(([category, items]) => {
    items.forEach((item, index) => {
      const tr = document.createElement("tr");
      tr.draggable = true;

      tr.innerHTML = `
        <td>${category}</td>
        <td contenteditable>${item.display_name}</td>
        <td contenteditable>${item.aliases.join(", ")}</td>
        <td contenteditable>${item.link}</td>
      `;

      tr.ondragstart = e => {
        e.dataTransfer.setData("text/plain", index);
        tr.dataset.category = category;
      };

      tr.ondragover = e => e.preventDefault();

      tr.ondrop = e => {
        const from = Number(e.dataTransfer.getData("text/plain"));
        const to = index;

        const arr = yamlData[category];
        const moved = arr.splice(from, 1)[0];
        arr.splice(to, 0, moved);

        renderTable();
      };

      tbody.appendChild(tr);
    });
  });
}

/* ------------------ MODAL ------------------ */

addBtn.onclick = () => {
  modalCategory.innerHTML = "";
  Object.keys(yamlData).forEach(cat => {
    const opt = document.createElement("option");
    opt.value = cat;
    opt.textContent = cat;
    modalCategory.appendChild(opt);
  });

  modalDisplayName.value = "";
  modalAliases.value = "";
  modalLink.value = "";

  modal.hidden = false;
};

modalCancel.onclick = () => {
  modal.hidden = true;
};

modalSave.onclick = () => {
  const category = modalCategory.value;
  const entry = {
    display_name: modalDisplayName.value.trim(),
    aliases: modalAliases.value
      .split(",")
      .map(a => a.trim().toLowerCase())
      .filter(Boolean),
    link: modalLink.value.trim()
  };

  yamlData[category].push(entry);
  modal.hidden = true;
  renderTable();
};

/* ------------------ VALIDATION ------------------ */

function validateSchema(data) {
  const errors = [];

  Object.entries(data).forEach(([cat, items]) => {
    items.forEach((item, i) => {
      if (!item.display_name) errors.push(`${cat}[${i}]: display_name missing`);
      if (!item.aliases?.length) errors.push(`${cat}[${i}]: aliases empty`);
      try {
        new URL(item.link);
      } catch {
        errors.push(`${cat}[${i}]: invalid link`);
      }
    });
  });

  return errors;
}

function findDuplicateAliases(data) {
  const seen = new Map();
  const warnings = [];

  Object.entries(data).forEach(([cat, items]) => {
    items.forEach(item => {
      item.aliases.forEach(alias => {
        if (seen.has(alias)) {
          warnings.push(`Alias "${alias}" duplicated`);
        } else {
          seen.set(alias, true);
        }
      });
    });
  });

  return warnings;
}

/* ------------------ SAVE ------------------ */

saveBtn.onclick = async () => {
  const errors = validateSchema(yamlData);
  if (errors.length) {
    alert("Errors:\n" + errors.join("\n"));
    return;
  }

  const warnings = findDuplicateAliases(yamlData);
  if (warnings.length) {
    const proceed = confirm(
      "Warnings:\n" + warnings.join("\n") + "\n\nSave anyway?"
    );
    if (!proceed) return;
  }

  const yamlText = dumpYaml(yamlData);
  const branch = await createBranch(token, baseSha);

  await commitFile(
    token,
    branch,
    yamlText,
    "Update bot mappings via editor",
    fileSha
  );

  await openPR(token, branch);
  alert("Pull request created");
};
