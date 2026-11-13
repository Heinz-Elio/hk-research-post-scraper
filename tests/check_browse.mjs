/**
 * Headless check of the browse helpers embedded in docs/index.html.
 * Run: node tests/check_browse.mjs
 */
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const html = readFileSync(new URL("../docs/index.html", import.meta.url), "utf8");
const script = html.match(/<script type="module">([\s\S]*?)<\/script>/);
if (!script) throw new Error("module script missing");

const syntax = spawnSync(process.execPath, ["--check", "--input-type=module"], {
  input: script[1],
  encoding: "utf8",
});
if (syntax.status !== 0) {
  console.error(syntax.stderr);
  process.exit(syntax.status || 1);
}

const block = html.match(/\/\* BROWSE_PURE_START \*\/([\s\S]*?)\/\* BROWSE_PURE_END \*\//);
if (!block) throw new Error("browse helpers missing");
const pureUrl = pathToFileURL("/tmp/browse-pure.mjs");
const { writeFileSync } = await import("node:fs");
writeFileSync("/tmp/browse-pure.mjs", `${block[1]}\nexport { todayISO, isUpcoming, sortPosts, workMatches, encodeBrowseState, decodeBrowseState };\n`);
const api = await import(pureUrl.href);

const today = "2026-11-13";
const posts = [
  { id: "past-review", date_type: "review_start", close_date: "2025-08-21", scraped_at: "2026-11-01" },
  { id: "soon", date_type: "deadline", close_date: "2026-11-20", scraped_at: "2026-10-01" },
  { id: "later", date_type: "deadline", close_date: "2026-12-01", scraped_at: "2026-11-02" },
  { id: "future-review", date_type: "review_start", close_date: "2026-11-18", scraped_at: "2026-09-01" },
  { id: "filled", date_type: "open_until_filled", close_date: null, scraped_at: "2026-11-10" },
  { id: "older-open", date_type: "unspecified", close_date: null, scraped_at: "2026-08-01" },
];

const ordered = api.sortPosts(posts, "close_date", today).map((p) => p.id);
if (JSON.stringify(ordered) !== JSON.stringify(["future-review", "soon", "later", "filled", "past-review", "older-open"])) {
  throw new Error(`unexpected default order: ${ordered.join(", ")}`);
}
const titled = posts.map((p, i) => ({ ...p, title: ["zeta", "alpha", "mu", "beta", "aa", "mid"][i] }));
const byTitle = api.sortPosts(titled, "title", today).map((p) => p.title);
if (JSON.stringify(byTitle) !== JSON.stringify(["aa", "alpha", "beta", "mid", "mu", "zeta"])) {
  throw new Error(`title sort broken: ${byTitle.join(", ")}`);
}
const byScrape = api.sortPosts(posts, "scraped_at", today).map((p) => p.id);
if (byScrape[0] !== "filled") throw new Error(`scraped sort broken: ${byScrape.join(", ")}`);

if (!api.workMatches({ work_type: "Full-time/Part-time" }, "Full-time")) throw new Error("Full-time should include both");
if (api.workMatches({ work_type: "Part-time" }, "Full-time")) throw new Error("Part-time is not Full-time");
if (!api.workMatches({ work_type: null }, "unspecified")) throw new Error("null is unspecified");
if (!api.workMatches({ work_type: "" }, "unspecified")) throw new Error("blank is unspecified");
if (api.workMatches({ work_type: "Full-time" }, "unspecified")) throw new Error("stated type is not unspecified");

const state = {
  src: "HKUST",
  work: "Full-time",
  held: "2",
  req: "master",
  contract: "6-12",
  place: "Hong Kong",
  deadline: "soon",
  sort: "title",
  q: "battery cells",
  page: 3,
  domains: ["ai-ml", "health"],
  short: true,
  hideApplied: true,
};
const encoded = api.encodeBrowseState(state);
const decoded = api.decodeBrowseState(encoded);
for (const key of Object.keys(state)) {
  const got = decoded[key];
  const expected = state[key];
  if (JSON.stringify(got) !== JSON.stringify(expected)) {
    throw new Error(`${key}: ${JSON.stringify(got)} !== ${JSON.stringify(expected)}`);
  }
}
if (api.encodeBrowseState({ sort: "close_date", page: 1, domains: [], q: "" }) !== "") {
  throw new Error("defaults should not be written into the query string");
}

const dataPath = new URL("../research_posts.json", import.meta.url);
let data;
try {
  data = JSON.parse(readFileSync(dataPath, "utf8"));
} catch {
  data = null;
}
if (data) {
  const old = data.slice().sort((a, b) => (a.close_date || "9999-12-31").localeCompare(b.close_date || "9999-12-31"));
  const next = api.sortPosts(data, "close_date", today);
  const real = (p) => p.date_type === "deadline" && p.close_date && p.close_date >= today;
  const upcoming = (p) => api.isUpcoming(p, today);
  const count = (list) => list.slice(0, 20).filter(real).length;
  const countUp = (list) => list.slice(0, 20).filter(upcoming).length;
  console.log(JSON.stringify({
    today,
    posts: data.length,
    page1_real_deadlines_before: count(old),
    page1_upcoming_before: countUp(old),
    page1_real_deadlines_after: count(next),
    page1_upcoming_after: countUp(next),
    page1_after: next.slice(0, 20).map((p) => ({ id: p.id, date_type: p.date_type, close_date: p.close_date })),
  }, null, 2));
}

console.log("browse helpers ok");
