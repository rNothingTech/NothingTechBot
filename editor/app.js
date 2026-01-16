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
let originalYamlContent = "";

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
    try {
        const result = await loadYaml(token);
        originalYamlContent = result.content; // Store the original string
        yamlData = parseYaml(result.content) || {};
        fileSha = result.sha;
        renderTable();
        updateSaveButtonState(); // Initialize button state
    } catch (err) {
        console.error(err);
        alert("Error loading YAML: " + err.message);
    } finally {
        setLoading(false);
    }
}

function updateSaveButtonState() {
    const currentYamlContent = dumpYaml(yamlData);
    // Disable button if content is identical
    els.saveBtn.disabled = (currentYamlContent.trim() === originalYamlContent.trim());
    
    // Optional: Add a visual cue
    if (els.saveBtn.disabled) {
        els.saveBtn.style.opacity = "0.5";
        els.saveBtn.style.cursor = "not-allowed";
    } else {
        els.saveBtn.style.opacity = "1";
        els.saveBtn.style.cursor = "pointer";
    }
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
                <td contenteditable="true" data-field="link" class="link-cell-text">${escapeHtml(item.link)}</td>
                <td>
                    <div class="action-buttons">
                        <button class="secondary copy-btn" title="Copy Link"><i class="fa-solid fa-copy"></i></button>
                        <button class="danger delete-btn" title="Delete"><i class="fa-solid fa-trash"></i></button>
                    </div>
                </td>
            `;

            // Event Listeners for this row
            attachRowEvents(tr, category, index);
            els.tbody.appendChild(tr);
        });
    });
}

function attachRowEvents(tr, category, index) {
    // 1. Live Editing (Standardized)
    const inputs = tr.querySelectorAll('[contenteditable]');
    inputs.forEach(el => {
        el.onblur = () => {
            const field = el.dataset.field;
            let val = el.innerText.trim();

            if (field === 'aliases') {
                yamlData[category][index].aliases = val.split(',').map(s => s.trim()).filter(Boolean);
            } else {
                yamlData[category][index][field] = val;
            }
            updateSaveButtonState();
        };
        
        // Prevent new lines on Enter
        el.onkeydown = (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                el.blur();
            }
        };
    });

    // 2. Copy Link Logic
    tr.querySelector('.copy-btn').onclick = () => {
        const url = yamlData[category][index].link;
        navigator.clipboard.writeText(url).then(() => {
            const btn = tr.querySelector('.copy-btn');
            const icon = btn.querySelector('i');
            // Visual feedback
            icon.className = 'fa-solid fa-check';
            btn.style.color = 'var(--primary)';
            setTimeout(() => {
                icon.className = 'fa-solid fa-copy';
                btn.style.color = '';
            }, 2000);
        });
    };

    // 3. Delete
    tr.querySelector('.delete-btn').onclick = () => {
        if (confirm(`Delete "${yamlData[category][index].display_name}"?`)) {
            yamlData[category].splice(index, 1);
            if (yamlData[category].length === 0) delete yamlData[category];
            renderTable(els.searchInput.value);
            updateSaveButtonState();
        }
    };

    // 4. Drag & Drop
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
        updateSaveButtonState()
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
    const aliasConflicts = [];
    Object.entries(yamlData).forEach(([existingCat, items]) => {
        items.forEach(item => {
            item.aliases.forEach(existingAlias => {
                if (aliases.includes(existingAlias)) {
                    aliasConflicts.push({
                        alias: existingAlias,
                        category: existingCat,
                        name: item.display_name
                    });
                }
            });
        });
    });

    if (aliasConflicts.length > 0) {
        const conflictMsgs = aliasConflicts.map(c => 
            `• "${c.alias}" (found in ${c.category} > ${c.name})`
        ).join('\n');

        if (!confirm(`Warning: The following aliases already exist:\n\n${conflictMsgs}\n\nDo you still want to add this command?`)) {
            return;
        }
    }

    const newItem = { display_name: name, aliases, link };

    if (!yamlData[cat]) yamlData[cat] = [];
    yamlData[cat].push(newItem);

    els.modal.hidden = true;
    renderTable(els.searchInput.value);
    updateSaveButtonState()
};

/* ------------------ SAVE ------------------ */
els.saveBtn.onclick = async () => {
    const currentYaml = dumpYaml(yamlData);
    
    if (currentYaml.trim() === originalYamlContent.trim()) {
        alert("No changes detected to save.");
        return;
    }

    // Ask user for a commit message
    const customMessage = prompt("Enter a commit message:", "Update commands.yaml via Editor");
    
    // If user clicks "Cancel", stop the save
    if (customMessage === null) return;

    const message = customMessage.trim() || "Update commands.yaml via Editor";

    setLoading(true, "Committing changes...");
    try {
        await saveToMain(token, currentYaml, fileSha, message);
        alert("Saved successfully!");
        await loadData(); // Reload to get new SHA and reset "original" state
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