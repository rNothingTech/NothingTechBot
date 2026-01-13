const CLIENT_ID = "Ov23liyqmUB7D5ZzIEMo";
const REPO = "AdaaamB/NothingTechBot";
const FILE_PATH = "commands.yaml";

export function login() {
  window.location.href =
    `https://github.com/login/oauth/authorize` +
    `?client_id=${CLIENT_ID}` +
    `&scope=repo` +
    `&redirect_uri=${location.href}`;
}

export async function getUser(token) {
  const res = await fetch("https://api.github.com/user", {
    headers: { Authorization: `Bearer ${token}` }
  });
  return res.json();
}

export async function isCollaborator(username, token) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/collaborators/${username}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  return res.status === 204;
}

export async function loadYaml(token) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/contents/${FILE_PATH}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const json = await res.json();
  return {
    content: atob(json.content),
    sha: json.sha
  };
}

export async function getMainSha(token) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/git/ref/heads/main`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const json = await res.json();
  return json.object.sha;
}

export async function createBranch(token, baseSha) {
  const name = `editor-${Date.now()}`;

  await fetch(`https://api.github.com/repos/${REPO}/git/refs`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      ref: `refs/heads/${name}`,
      sha: baseSha
    })
  });

  return name;
}

export async function commitFile(token, branch, content, message, sha) {
  await fetch(
    `https://api.github.com/repos/${REPO}/contents/${FILE_PATH}`,
    {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        message,
        content: btoa(content),
        branch,
        sha
      })
    }
  );
}

export async function openPR(token, branch) {
  await fetch(`https://api.github.com/repos/${REPO}/pulls`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      title: "Update bot mappings",
      head: branch,
      base: "main"
    })
  });
}
