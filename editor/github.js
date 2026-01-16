const CLIENT_ID = "Ov23liyqmUB7D5ZzIEMo";
const REPO = "rNothingTech/NothingTechBot";
const FILE_PATH = "commands.yaml"; // Defined in root as per prompt

export function saveToken(token) {
  localStorage.setItem("gh_token", token);
  window.location.reload();
}

export function logout() {
  localStorage.removeItem("gh_token");
  window.location.reload();
}

export function getAccessToken() {
  return localStorage.getItem("gh_token");
}

export async function getUser(token) {
    const res = await fetch("https://api.github.com/user", {
        headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) throw new Error("Failed to fetch user");
    return res.json();
}

export async function isCollaborator(username, token) {
    const res = await fetch(`https://api.github.com/repos/${REPO}/collaborators/${username}`, {
        headers: { Authorization: `Bearer ${token}` }
    });
    return res.status === 204;
}

export async function loadYaml(token) {
    const res = await fetch(`https://api.github.com/repos/${REPO}/contents/${FILE_PATH}`, {
        headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) throw new Error("Failed to load YAML file");
    const json = await res.json();
    // Handle UTF-8 decoding properly
    const content = new TextDecoder().decode(Uint8Array.from(atob(json.content), c => c.charCodeAt(0)));
    return { content, sha: json.sha };
}

export async function saveToMain(token, content, oldSha, message) {
    // 1. Encode content to Base64 (UTF-8 safe)
    const binaryStr = new TextEncoder().encode(content).reduce((a, b) => a + String.fromCharCode(b), '');
    const b64Content = btoa(binaryStr);

    // 2. PUT to file path
    const res = await fetch(`https://api.github.com/repos/${REPO}/contents/${FILE_PATH}`, {
        method: "PUT",
        headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            message,
            content: b64Content,
            sha: oldSha, // Required to update existing file
            branch: "main" // Direct commit
        })
    });

    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.message || "Save failed");
    }

    return res.json();
}