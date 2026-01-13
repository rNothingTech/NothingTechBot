const CLIENT_ID = "Ov23liyqmUB7D5ZzIEMo";
const REPO = "AdaaamB/NothingTechBot";
const FILE_PATH = "commands.yaml";

export function login() {
  const redirectUri = window.location.origin + window.location.pathname;
  const scopes = "repo read:user";

  window.location.href =
    `https://github.com/login/oauth/authorize` +
    `?client_id=${CLIENT_ID}` +
    `&redirect_uri=${encodeURIComponent(redirectUri)}` +
    `&scope=${encodeURIComponent(scopes)}` +
    `&response_type=token`;
}

export function getAccessToken() {
  if (window.location.hash.includes("access_token")) {
    const params = new URLSearchParams(window.location.hash.substring(1));
    const token = params.get("access_token");
    localStorage.setItem("gh_token", token);
    window.location.hash = "";
    return token;
  }
  return localStorage.getItem("gh_token");
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
