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
const pure = `${block[1]}\nexport { todayISO, isUpcoming, sortPosts, workMatches, encodeBrowseState, decodeBrowseState, searchPosts, buildCardBrief };\n`;
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

const briefFixture = {
  title: "Research Assistant",
  department: "Department of History",
  summary: [
    "- Dept: Department of History",
    "- Role focus: The appointee will be responsible for conducting literature reviews and writing research reports.",
    "- Requirements: A bachelor's degree in history or related disciplines; Python is preferred.",
    "- Appointment: 12 months, renewable",
    "- Closing: 2026-12-01",
  ].join("\n"),
};
const brief = api.buildCardBrief(briefFixture);
assert.deepEqual(brief.items, [
  ["Work", "Literature reviews, Report writing"],
  ["Study background", "history or related disciplines"],
  ["Skills mentioned", "Python"],
]);
assert.ok(brief.excerpts.some(([label, text]) => label === "Requirements" && text.includes("Python is preferred.")));
assert.ok(!brief.excerpts.some(([label]) => label === "Closing" || label === "Dept"));
assert.equal(api.searchPosts([{ ...briefFixture, id: "brief" }], "renewable").length, 1);

const projectTitle = "Community-led documentation of architectural heritage, archival records, and changing patterns of public space and cultural participation in neighbourhoods across the city";
const projectBrief = api.buildCardBrief({
  title: "Research Assistant",
  project: projectTitle,
  summary: `- Project: ${projectTitle}\n- Role focus: The appointee will assist the project leader in the research project - "${projectTitle}".`,
});
assert.deepEqual(projectBrief.items.map(([label]) => label), ["Project"]);
assert.ok(projectBrief.items[0][1].length < projectTitle.length);
assert.deepEqual(projectBrief.excerpts, [["Project", projectTitle]]);
assert.deepEqual(api.buildCardBrief({
  title: "Research Assistant",
  summary: "- Dept: History\n- Role focus: Research Assistant\n- Closing: 2026-12-01",
}), { items: [], excerpts: [] });
assert.deepEqual(api.buildCardBrief({
  title: "Research Assistant",
  summary: "- Project: Tasks\n- Role focus: Work under the supervision of the head of the unit.\n- Requirements: a degree in a relevant field (e.g. engineering); Python",
}).items, [["Skills mentioned", "Python"]]);

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
