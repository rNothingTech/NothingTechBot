import {
    saveToken,
    logout,
    getAccessToken,
    getUser,
    isCollaborator,
    loadYaml,
    saveToMain
} from "./github.js";
import { parseYaml, dumpYaml } from "./yaml.js";

/* ------------------ STATE ------------------ */
let token = null;
let yamlData = {}; // { category: [items] }
let fileSha = null;

/* ------------------ DOM ELEMENTS ------------------ */
const els = {
    app: document.getElementById("app"),
    tokenInput: document.getElementById("tokenInput"),
    saveTokenBtn: document.getElementById("saveTokenBtn"),
    authSection: document.getElementById("authSection"),
    userSection: document.getElementById("userSection"),
    logoutBtn: document.getElementById("logoutBtn"),
    userInfo: document.getElementById("userInfo"),
    tbody: document.querySelector("#mappingsTable tbody"),
    addBtn: document.getElementById("addBtn"),
    saveBtn: document.getElementById("saveBtn"),
    searchInput: document.getElementById("searchInput"),

    // Modal
    modal: document.getElementById("modal"),
    modalCategory: document.getElementById("modalCategory"),
    categoryList: document.getElementById("categoryList"),
    modalDisplayName: document.getElementById("modalDisplayName"),
    modalAliases: document.getElementById("modalAliases"),
    modalLink: document.getElementById("modalLink"),
    modalSave: document.getElementById("modalSave"),
    modalCancel: document.getElementById("modalCancel"),

    // Loading
    loader: document.getElementById("loadingOverlay"),
    loaderText: document.getElementById("loadingText"),
};

/* ------------------ INITIALIZATION ------------------ */
els.saveTokenBtn.onclick = () => {
  const t = els.tokenInput.value.trim();
  if (t) saveToken(t);
};

els.logoutBtn.onclick = logout;

async function bootstrap() {
    token = getAccessToken();
  
    if (!token) {
        els.authSection.hidden = false;
        els.userSection.hidden = true;
        els.app.hidden = true;
        return; 
    }

    els.authSection.hidden = true;
    els.userSection.hidden = false;

    setLoading(true, "Authenticating with GitHub...");

    try {
        const user = await getUser(token);

        // Error handling for bad tokens
        if (user.message === "Bad credentials") {
            throw new Error("Invalid GitHub Token. Please clear and try again.");
        }

        // Update UI with username
        els.userInfo.textContent = `Signed in as ${user.login}`;
        
        // 3. Permission Check
        const allowed = await isCollaborator(user.login, token);
        if (!allowed) {
            throw new Error("You do not have write access to the NothingTechBot repository.");
        }

        // 4. Data Loading
        await loadData();
        els.app.hidden = false;

    } catch (err) {
        console.error(err);
        alert(err.message);
        // If the token is invalid, it's often best to log out automatically
        if (err.message.includes("Invalid")) logout();
    } finally {
        setLoading(false);
    }
}

async function loadData() {
    setLoading(true, "Fetching commands.yaml...");
    const result = await loadYaml(token);
    yamlData = parseYaml(result.content) || {};
    fileSha = result.sha;
    renderTable();
    setLoading(false);
}

bootstrap();

/* ------------------ RENDER & EDITING ------------------ */
function renderTable(filter = "") {
    els.tbody.innerHTML = "";
    const filterText = filter.toLowerCase();

    Object.entries(yamlData).forEach(([category, items]) => {
        // If empty category, keep it in state but maybe not render? 
        // Or render a placeholder? We'll skip for now if empty.
        if (!items || !Array.isArray(items)) return;

        items.forEach((item, index) => {
            // Search Filtering
            const str = `${category} ${item.display_name} ${item.aliases.join(" ")}`.toLowerCase();
            if (filter && !str.includes(filterText)) return;

            const tr = document.createElement("tr");
            tr.draggable = true;
            tr.dataset.category = category;
            tr.dataset.index = index;

            tr.innerHTML = `
        <td class="drag-handle"><i class="fa-solid fa-grip-vertical"></i></td>
        <td>${category}</td>
        <td contenteditable="true" data-field="display_name">${escapeHtml(item.display_name)}</td>
        <td contenteditable="true" data-field="aliases">${escapeHtml(item.aliases.join(", "))}</td>
        <td contenteditable="true" data-field="link"><a href="${item.link}" target="_blank"><i class="fa-solid fa-link"></i></a> ${escapeHtml(item.link)}</td>
        <td>
          <button class="danger delete-btn"><i class="fa-solid fa-trash"></i></button>
        </td>
      `;

            // Event Listeners for this row
            attachRowEvents(tr, category, index);
            els.tbody.appendChild(tr);
        });
    });
}

function attachRowEvents(tr, category, index) {
    // 1. Live Editing
    const inputs = tr.querySelectorAll('[contenteditable]');
    inputs.forEach(td => {
        td.onblur = (e) => {
            const field = td.dataset.field;
            let val = td.innerText.trim();

            // Update State
            if (field === 'aliases') {
                const arr = val.split(',').map(s => s.trim()).filter(Boolean);
                yamlData[category][index].aliases = arr;
            } else {
                yamlData[category][index][field] = val;
            }
        };
    });

    // 2. Delete
    tr.querySelector('.delete-btn').onclick = () => {
        if (confirm(`Delete "${yamlData[category][index].display_name}"?`)) {
            yamlData[category].splice(index, 1);
            // Clean up empty categories if desired
            if (yamlData[category].length === 0) delete yamlData[category];
            renderTable(els.searchInput.value);
        }
    };

    // 3. Drag & Drop
    tr.ondragstart = e => {
        e.dataTransfer.setData("application/json", JSON.stringify({ category, index }));
        tr.classList.add("dragging");
    };
    tr.ondragend = () => tr.classList.remove("dragging");

    tr.ondragover = e => e.preventDefault(); // Allow dropping

    tr.ondrop = e => {
        e.preventDefault();
        const dragData = JSON.parse(e.dataTransfer.getData("application/json"));
        const sourceCat = dragData.category;
        const sourceIdx = dragData.index;

        // Target (where we dropped)
        const targetCat = category; // from closure
        const targetIdx = index;    // from closure

        // Remove from source
        const [movedItem] = yamlData[sourceCat].splice(sourceIdx, 1);

        // Cleanup source cat if empty
        if (yamlData[sourceCat].length === 0 && sourceCat !== targetCat) {
            delete yamlData[sourceCat];
        }

        // Insert into target
        if (!yamlData[targetCat]) yamlData[targetCat] = [];
        yamlData[targetCat].splice(targetIdx, 0, movedItem);

        renderTable(els.searchInput.value);
    };
}

els.searchInput.oninput = (e) => renderTable(e.target.value);

/* ------------------ MODAL ACTIONS ------------------ */
els.addBtn.onclick = () => {
    // Populate datalist with existing categories
    els.categoryList.innerHTML = "";
    Object.keys(yamlData).forEach(cat => {
        const opt = document.createElement("option");
        opt.value = cat;
        els.categoryList.appendChild(opt);
    });

    // Clear inputs
    els.modalCategory.value = "";
    els.modalDisplayName.value = "";
    els.modalAliases.value = "";
    els.modalLink.value = "";

    els.modal.hidden = false;
};

els.modalCancel.onclick = () => els.modal.hidden = true;

els.modalSave.onclick = () => {
    const cat = els.modalCategory.value.trim();
    const name = els.modalDisplayName.value.trim();
    const aliases = els.modalAliases.value.split(',').map(a => a.trim().toLowerCase()).filter(Boolean);
    const link = els.modalLink.value.trim();

    if (!cat || !name || !link) {
        alert("Please fill in Category, Display Name, and Link.");
        return;
    }

    // Duplicate Check
    const allAliases = [];
    Object.values(yamlData).flat().forEach(i => allAliases.push(...i.aliases));
    const conflicts = aliases.filter(a => allAliases.includes(a));

    if (conflicts.length > 0) {
        if (!confirm(`Warning: The alias(es) "${conflicts.join(', ')}" already exist. Add anyway?`)) {
            return;
        }
    }

    const newItem = { display_name: name, aliases, link };

    if (!yamlData[cat]) yamlData[cat] = [];
    yamlData[cat].push(newItem);

    els.modal.hidden = true;
    renderTable(els.searchInput.value);
};

/* ------------------ SAVE ------------------ */
els.saveBtn.onclick = async () => {
    if (!confirm("Are you sure you want to save changes to the repository?")) return;

    setLoading(true, "Committing changes...");
    try {
        const yamlStr = dumpYaml(yamlData);
        await saveToMain(token, yamlStr, fileSha, "Update commands.yaml via Editor");
        alert("Saved successfully!");
        // Reload to get new SHA
        await loadData();
    } catch (err) {
        console.error(err);
        alert("Failed to save: " + err.message);
        setLoading(false);
    }
};

/* ------------------ UTILS ------------------ */
function setLoading(isLoading, text = "") {
    els.loader.hidden = !isLoading;
    els.loaderText.textContent = text;
}

function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}