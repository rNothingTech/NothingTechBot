import yaml from "https://cdn.jsdelivr.net/npm/js-yaml@4/dist/js-yaml.mjs";

export function parseYaml(text) {
  return yaml.load(text);
}

export function dumpYaml(data) {
  return yaml.dump(data, {
    noRefs: true,
    sortKeys: false,
    lineWidth: 120
  });
}
