/**
 * Headless check of the browse helpers embedded in docs/index.html.
 * Run: node tests/check_browse.mjs
 */
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";

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
const pure = `${block[1]}\nexport { todayISO, isUpcoming, sortPosts, workMatches, encodeBrowseState, decodeBrowseState, searchPosts };\n`;
const api = await import(`data:text/javascript,${encodeURIComponent(pure)}`);

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

const searchFixture = [
  { id: "noise", title: "Administration", scraped_at: "2026-11-12" },
  { id: "project", title: "Research Assistant", project: "Remote sensing with GIS", scraped_at: "2026-11-05", close_date: "2026-12-01" },
  { id: "related", title: "Satellite image mapping", scraped_at: "2026-11-07", close_date: "2026-11-20" },
  { id: "weak", title: "Agricultural policy", scraped_at: "2026-11-11" },
  { id: "stats", title: "Statistical support", summary: "- Requirements: Proficiency in R and C++." },
  { id: "other", title: "C# and Ruby programming", summary: "- Role focus: Survey team." },
  { id: "han", title: "\u7814\u7a76\u4f7f\u7528\u9059\u611f\u5f71\u50cf" },
];
const searchVectors = {
  noise: { q: [0, 127], scale: 0.01 },
  related: { q: [100, 10], scale: 0.02 },
  weak: { q: [18, 100], scale: 0.01 },
};
const ids = (rows) => rows.map((row) => row.id);
assert.deepEqual(ids(api.searchPosts(searchFixture, "R", { queryVector: [1, 0], vectors: searchVectors })), ["stats"]);
assert.deepEqual(ids(api.searchPosts(searchFixture, "C++")), ["stats"]);
assert.deepEqual(ids(api.searchPosts(searchFixture, "\u9059\u611f")), ["han"]);
assert.deepEqual(ids(api.searchPosts(searchFixture, "\u5730\u7406", {
  queryVector: [1, 0], vectors: { related: { q: [23, 100], scale: 0.01 } },
})), ["related"]);
assert.deepEqual(ids(api.searchPosts(searchFixture, "and the")), []);
assert.deepEqual(ids(api.searchPosts(searchFixture, "remote sensing", { sortBy: "scraped_at" })), ["project"]);
const remote = { queryVector: [1, 0], vectors: searchVectors };
assert.deepEqual(ids(api.searchPosts(searchFixture, "remote sensing", remote)), ["project", "related"]);
assert.deepEqual(ids(api.searchPosts(searchFixture, "remote sensing", { ...remote, sortBy: "scraped_at" })), ["related", "project"]);
assert.deepEqual(ids(api.searchPosts(searchFixture, "remote sensing", { ...remote, sortBy: "title" })), ["project", "related"]);
assert.deepEqual(ids(api.searchPosts(searchFixture, "remote sensing", { ...remote, sortBy: "close_date", today })), ["related", "project"]);
assert.equal(api.searchPosts(searchFixture, "", { ...remote, sortBy: "title" }).length, searchFixture.length);

const rankedFields = [
  { id: "summary", title: "Research Assistant", summary: "- Role focus: Analyse satellite imagery." },
  { id: "skills", title: "Research Fellow", summary: "- Requirements: Experience with satellite imagery." },
  { id: "title", title: "Satellite imagery specialist" },
];
assert.deepEqual(ids(api.searchPosts(rankedFields, "satellite imagery")), ["title", "skills", "summary"]);

const extra = Array.from({ length: 55 }, (_, i) => ({ id: `extra-${i}`, title: "Imagery role" }));
const extraVectors = Object.fromEntries(extra.map((row) => [row.id, { q: [100, 5], scale: 0.01 }]));
assert.equal(api.searchPosts(extra, "geospatial", { queryVector: [1, 0], vectors: extraVectors }).length, 40);

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
if (!encoded.startsWith("#")) throw new Error("share links must use a URL fragment");
for (const key of ["src", "work", "req", "contract", "place", "deadline", "sort", "domains"]) {
  const got = decoded[key];
  const expected = state[key];
  if (JSON.stringify(got) !== JSON.stringify(expected)) {
    throw new Error(`${key}: ${JSON.stringify(got)} !== ${JSON.stringify(expected)}`);
  }
}
const legacy = api.decodeBrowseState("?src=HKUST&q=private+query&held=2&short=1&hideApplied=1&page=3&sort=relevance");
const legacyOut = new URLSearchParams(encoded.slice(1));
for (const key of ["q", "held", "short", "hideApplied", "page"]) {
  if (legacyOut.has(key) || key in decoded || key in legacy) throw new Error(`private state exposed: ${key}`);
}
if (legacy.src !== "HKUST" || legacy.sort !== "close_date") throw new Error("legacy links should keep safe filters");
if (api.encodeBrowseState({ sort: "relevance", page: 1, domains: [], q: "private" }) !== "") {
  throw new Error("defaults and private state should not be written into links");
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
